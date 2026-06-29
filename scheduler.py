"""
Operation scheduler / executor.

Sending strategy
----------------
For each target email T and each selected sender S (in order):
    1. Send email from S → T
    2. Wait a random number of seconds in [delay_min, delay_max]
       (skipped after the very last send of the whole operation)

This means every target inbox receives one email from every selected
sender, spaced out by unpredictable gaps to avoid spam clustering.
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Set

from sqlalchemy import select

from database import AsyncSessionLocal
from gmail_service import get_app_password, send_email
from models import (
    GmailAccount,
    Operation,
    OperationSend,
    OperationSender,
    TargetEmail,
    TargetList,
    User,
)

logger = logging.getLogger(__name__)

# Track which operation IDs are currently executing so we never double-run.
_active_operations: Set[int] = set()


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def launch_operation(operation_id: int) -> None:
    """Kick off an operation in a background asyncio task (non-blocking)."""
    if operation_id in _active_operations:
        logger.warning("Operation %d is already running – skipping duplicate launch.", operation_id)
        return
    _active_operations.add(operation_id)
    asyncio.create_task(_run_operation(operation_id))


async def resume_interrupted_operations() -> None:
    """Called on bot startup. Re-launches any operations stuck in 'sending' state."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Operation).where(Operation.status == "sending")
        )
        stuck = result.scalars().all()

    for op in stuck:
        if op.id not in _active_operations:
            logger.info("Resuming interrupted operation ID %d.", op.id)
            await launch_operation(op.id)


# ---------------------------------------------------------------------------
# Core worker
# ---------------------------------------------------------------------------

async def _run_operation(operation_id: int) -> None:
    try:
        await _execute(operation_id)
    except Exception:
        logger.exception("Unexpected failure in operation %d.", operation_id)
        async with AsyncSessionLocal() as session:
            op = await session.get(Operation, operation_id)
            if op:
                op.status = "failed"
                await session.commit()
    finally:
        _active_operations.discard(operation_id)


async def _execute(operation_id: int) -> None:
    from bot import bot  # deferred to avoid circular import

    # ------------------------------------------------------------------ setup
    async with AsyncSessionLocal() as session:
        operation = await session.get(Operation, operation_id)
        if not operation:
            logger.error("Operation %d not found.", operation_id)
            return

        operation.status = "sending"
        await session.commit()

        # Load selected sender accounts
        sender_rows_result = await session.execute(
            select(OperationSender).where(OperationSender.operation_id == operation_id)
        )
        sender_rows = sender_rows_result.scalars().all()

        sender_accounts: list[GmailAccount] = []
        for row in sender_rows:
            acc = await session.get(GmailAccount, row.gmail_account_id)
            if acc:
                sender_accounts.append(acc)

        if not sender_accounts:
            await _fail(session, operation, "No sender accounts linked to this operation.", bot)
            return

        # Load pending sends (supports resume after crash)
        pending_result = await session.execute(
            select(OperationSend).where(
                OperationSend.operation_id == operation_id,
                OperationSend.status == "pending",
            )
        )
        pending_sends = pending_result.scalars().all()

        # Load target emails and app passwords for each sender
        targets: dict[int, TargetEmail] = {}
        for send in pending_sends:
            if send.target_email_id not in targets:
                te = await session.get(TargetEmail, send.target_email_id)
                if te:
                    targets[send.target_email_id] = te

        senders: dict[int, tuple[GmailAccount, str]] = {}
        for acc in sender_accounts:
            try:
                pw = await get_app_password(acc.id)
                senders[acc.id] = (acc, pw)
            except Exception as exc:
                logger.warning("Could not load credentials for %s: %s", acc.email, exc)

        owner = await session.get(User, operation.user_id)
        telegram_chat_id = owner.telegram_id if owner else None
        subject = operation.subject
        body = operation.body
        delay_min = operation.delay_min
        delay_max = operation.delay_max

        # Load total sends count
        total_sends_result = await session.execute(
            select(OperationSend).where(OperationSend.operation_id == operation_id)
        )
        total = len(total_sends_result.scalars().all())
        sent_count = operation.sent_count
        failed_count = operation.failed_count

    if not senders:
        async with AsyncSessionLocal() as session:
            op = await session.get(Operation, operation_id)
            if op:
                await _fail(session, op, "Could not authenticate any sender accounts.", bot)
        return

    # ------------------------------------------------------------------ send loop
    start_time = time.time()
    senders_count = len(sender_accounts)
    initial_sent_count = sent_count
    initial_failed_count = failed_count

    def format_time(seconds: float) -> str:
        s = max(0, int(seconds))
        mins = s // 60
        secs = s % 60
        return f"{mins:02d}:{secs:02d}"

    def make_progress_text(sent_c: int, failed_c: int, total_c: int, elapsed_s: float) -> str:
        processed = sent_c + failed_c
        active_processed = processed - (initial_sent_count + initial_failed_count)
        if active_processed > 0:
            avg_time = elapsed_s / active_processed
            rem_s = int((total_c - processed) * avg_time)
        else:
            avg_delay = (delay_min + delay_max) / 2.0 + 1.0
            rem_s = int((total_c - processed) * avg_delay)
        return (
            f"📨 Operation in progress...\n"
            f"Subject: {subject}\n"
            f"Progress: {processed} / {total_c} sends\n"
            f"✅ Sent: {sent_c}\n"
            f"❌ Failed: {failed_c}\n"
            f"⏱ Elapsed: {format_time(elapsed_s)}\n"
            f"⏳ Remaining: ~{format_time(rem_s)}"
        )

    progress_msg = None
    if telegram_chat_id:
        try:
            progress_msg = await bot.send_message(
                chat_id=telegram_chat_id,
                text=make_progress_text(sent_count, failed_count, total, 0.0)
            )
        except Exception as exc:
            logger.warning("Could not send initial progress message: %s", exc)

    last_update_count = sent_count + failed_count
    last_update_time = start_time

    for idx, send_record in enumerate(pending_sends):
        target = targets.get(send_record.target_email_id)
        sender_info = senders.get(send_record.gmail_account_id)

        if not target or not sender_info:
            async with AsyncSessionLocal() as session:
                sr = await session.get(OperationSend, send_record.id)
                op = await session.get(Operation, operation_id)
                if sr and op:
                    sr.status = "failed"
                    sr.error_message = "Target or sender missing."
                    op.failed_count += 1
                    await session.commit()
            failed_count += 1
            # Update progress check
            processed = sent_count + failed_count
            now_time = time.time()
            if progress_msg and (processed - last_update_count >= 5 or now_time - last_update_time >= 30 or idx == len(pending_sends) - 1):
                elapsed = now_time - start_time
                text = make_progress_text(sent_count, failed_count, total, elapsed)
                try:
                    await bot.edit_message_text(
                        chat_id=telegram_chat_id,
                        message_id=progress_msg.message_id,
                        text=text,
                    )
                    last_update_count = processed
                    last_update_time = now_time
                except Exception as exc:
                    logger.warning("Failed to edit progress message: %s", exc)
            continue

        acc, pw = sender_info
        success = False
        last_error = ""

        for attempt in range(3):
            try:
                await send_email(acc.email, pw, target.email, subject, body)
                success = True
                break
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Send attempt %d failed (%s → %s): %s",
                    attempt + 1, acc.email, target.email, last_error,
                )
                if any(code in last_error for code in ("535", "invalid_grant", "AuthenticationFailed")):
                    logger.error("Fatal auth error on %s – removing from pool.", acc.email)
                    senders.pop(acc.id, None)
                    break
                await asyncio.sleep(2 ** attempt)

        async with AsyncSessionLocal() as session:
            sr = await session.get(OperationSend, send_record.id)
            op = await session.get(Operation, operation_id)
            if sr and op:
                if success:
                    sr.status = "sent"
                    sr.sent_at = datetime.utcnow()
                    op.sent_count += 1
                    sent_count += 1
                else:
                    sr.status = "failed"
                    sr.error_message = last_error
                    op.failed_count += 1
                    failed_count += 1
                await session.commit()

        # Update progress check
        processed = sent_count + failed_count
        now_time = time.time()
        if progress_msg and (processed - last_update_count >= 5 or now_time - last_update_time >= 30 or idx == len(pending_sends) - 1):
            elapsed = now_time - start_time
            text = make_progress_text(sent_count, failed_count, total, elapsed)
            try:
                await bot.edit_message_text(
                    chat_id=telegram_chat_id,
                    message_id=progress_msg.message_id,
                    text=text,
                )
                last_update_count = processed
                last_update_time = now_time
            except Exception as exc:
                logger.warning("Failed to edit progress message: %s", exc)

        # Random delay between sends (skip after the very last one)
        if idx < len(pending_sends) - 1:
            delay = random.uniform(delay_min, delay_max)
            logger.debug("Waiting %.1fs before next send.", delay)
            await asyncio.sleep(delay)

    # ------------------------------------------------------------------ complete
    total_time = time.time() - start_time

    async with AsyncSessionLocal() as session:
        op = await session.get(Operation, operation_id)
        list_name = "Unknown"
        if op:
            if op.status == "sending":
                op.status = "completed"
            
            # Load list name
            lst = await session.get(TargetList, op.list_id)
            if lst:
                list_name = lst.name
            await session.commit()

        # Query all failures for this operation
        failed_lines = []
        if failed_count > 0:
            failed_sends_result = await session.execute(
                select(OperationSend)
                .where(OperationSend.operation_id == operation_id, OperationSend.status == "failed")
            )
            failed_sends = failed_sends_result.scalars().all()
            for fs in failed_sends:
                target_email = await session.get(TargetEmail, fs.target_email_id)
                email_str = target_email.email if target_email else "Unknown"
                reason_str = fs.error_message or "Unknown error"
                failed_lines.append(f"• {email_str} ({reason_str})")

    if telegram_chat_id:
        summary_text = (
            f"✅ Operation Complete!\n"
            f"Subject: {subject}\n"
            f"Target list: {list_name}\n"
            f"Senders used: {senders_count}\n"
            f"📊 Results:\n"
            f"✅ Successfully sent: {sent_count}\n"
            f"❌ Failed: {failed_count}\n"
            f"📦 Total: {total}\n"
            f"⏱ Time taken: {format_time(total_time)}"
        )
        if failed_lines:
            lines_to_show = failed_lines[:20]
            summary_text += "\n\n" + "\n".join(lines_to_show)
            if len(failed_lines) > 20:
                summary_text += f"\n...and {len(failed_lines) - 20} more"

        try:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=summary_text,
            )
        except Exception as exc:
            logger.warning("Could not send terminal summary message: %s", exc)


async def _fail(session, operation: Operation, reason: str, bot) -> None:
    operation.status = "failed"
    await session.commit()
    owner = await session.get(User, operation.user_id)
    if owner:
        try:
            await bot.send_message(
                chat_id=owner.telegram_id,
                text=f"❌ *Operation failed*\n\nReason: `{reason}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass
