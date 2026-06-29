"""
Operation creation flow
-----------------------
Step 1  – Pick target list
Step 2  – Select one or more Gmail senders (multi-select toggle keyboard)
Step 3  – Enter subject
Step 4  – Enter body  (plain text or HTML)
Step 5  – Choose delay between sends (preset or custom)
Step 6  – Confirm and launch
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards import (
    get_cancel_keyboard,
    get_confirmation_keyboard,
    get_delay_keyboard,
    get_dynamic_selection_keyboard,
    get_operations_menu_keyboard,
    get_sender_selection_keyboard,
)
from bot.states import OperationStates
from database import AsyncSessionLocal
from models import (
    GmailAccount,
    Operation,
    OperationSend,
    OperationSender,
    TargetEmail,
    TargetList,
    User,
)
from scheduler import launch_operation

router = Router()


# ── View operations ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "op:list")
async def process_view_operations(callback: CallbackQuery, db_user: User):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Operation)
            .where(Operation.user_id == db_user.id)
            .order_by(Operation.created_at.desc())
        )
        ops = result.scalars().all()

        details = []
        for op in ops:
            lst = await session.get(TargetList, op.list_id)
            list_name = lst.name if lst else "?"
            total_result = await session.execute(
                select(OperationSend).where(OperationSend.operation_id == op.id)
            )
            total = len(total_result.scalars().all())
            details.append(
                f"📧 *{op.subject}*\n"
                f"  List: {list_name} | Status: `{op.status.upper()}`\n"
                f"  Sent: `{op.sent_count}` / Failed: `{op.failed_count}` / Total: `{total}`"
            )

    text = (
        "📧 *Your Operations:*\n\n" + "\n\n".join(details)
        if details
        else "📧 *No operations yet.*\n\nCreate one using the menu below."
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_operations_menu_keyboard())
    await callback.answer()


# ── Step 1 – Pick target list ─────────────────────────────────────────────────

@router.callback_query(F.data == "op:create")
async def process_create_step1(callback: CallbackQuery, state: FSMContext, db_user: User):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TargetList).where(TargetList.user_id == db_user.id)
        )
        lists = result.scalars().all()

    if not lists:
        await callback.message.edit_text(
            "❌ You have no target lists yet. Add one first.",
            reply_markup=get_operations_menu_keyboard(),
        )
        await callback.answer()
        return

    options = [(lst.name, f"op_list:{lst.id}") for lst in lists]
    await state.set_state(OperationStates.selecting_target_list)
    await callback.message.edit_text(
        "📧 *New Operation — Step 1*\n\nChoose a target list:",
        parse_mode="Markdown",
        reply_markup=get_dynamic_selection_keyboard(options, "operations"),
    )
    await callback.answer()


# ── Step 2 – Select senders ───────────────────────────────────────────────────

@router.callback_query(OperationStates.selecting_target_list, F.data.startswith("op_list:"))
async def process_list_selected(callback: CallbackQuery, state: FSMContext, db_user: User):
    list_id = int(callback.data.split(":")[1])
    await state.update_data(list_id=list_id, selected_sender_ids=[])

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GmailAccount).where(GmailAccount.user_id == db_user.id)
        )
        accounts = result.scalars().all()

    if not accounts:
        await callback.message.edit_text(
            "❌ No Gmail accounts added yet. Add one first.",
            reply_markup=get_operations_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    await state.update_data(accounts=[{"id": a.id, "email": a.email} for a in accounts])
    await state.set_state(OperationStates.selecting_senders)
    await callback.message.edit_text(
        "✉️ *Step 2 — Select Senders*\n\n"
        "Toggle accounts on/off. You can pick one or all of them.\n"
        "Each selected sender will send to every target.",
        parse_mode="Markdown",
        reply_markup=get_sender_selection_keyboard(accounts, set()),
    )
    await callback.answer()


@router.callback_query(OperationStates.selecting_senders, F.data.startswith("toggle_sender:"))
async def process_toggle_sender(callback: CallbackQuery, state: FSMContext, db_user: User):
    sender_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    selected: set[int] = set(data.get("selected_sender_ids", []))

    if sender_id in selected:
        selected.discard(sender_id)
    else:
        selected.add(sender_id)

    await state.update_data(selected_sender_ids=list(selected))

    # Rebuild keyboard with updated selection state
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GmailAccount).where(GmailAccount.user_id == db_user.id)
        )
        accounts = result.scalars().all()

    await callback.message.edit_reply_markup(
        reply_markup=get_sender_selection_keyboard(accounts, selected)
    )
    await callback.answer()


@router.callback_query(OperationStates.selecting_senders, F.data == "confirm_senders")
async def process_confirm_senders(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_sender_ids", [])

    if not selected:
        await callback.answer("Select at least one sender first.", show_alert=True)
        return

    await state.set_state(OperationStates.entering_subject)
    await callback.message.edit_text(
        f"✅ {len(selected)} sender(s) selected.\n\n"
        "📝 *Step 3 — Subject*\n\nType the email subject line:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("operations"),
    )
    await callback.answer()


# ── Step 3 – Subject ──────────────────────────────────────────────────────────

@router.message(OperationStates.entering_subject)
async def process_subject(message: Message, state: FSMContext):
    subject = message.text.strip()
    if not subject or len(subject) > 500:
        await message.answer("❌ Subject must be 1–500 characters. Try again:")
        return
    await state.update_data(subject=subject)
    await state.set_state(OperationStates.entering_body)
    await message.answer(
        "✉️ *Step 4 — Email Body*\n\n"
        "Send the message body. Plain text or HTML both work.",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("operations"),
    )


# ── Step 4 – Body ─────────────────────────────────────────────────────────────

@router.message(OperationStates.entering_body)
async def process_body(message: Message, state: FSMContext):
    body = message.text.strip()
    if not body:
        await message.answer("❌ Body cannot be empty. Try again:")
        return
    await state.update_data(body=body)
    await state.set_state(OperationStates.choosing_delay)
    await message.answer(
        "⏱ *Step 5 — Delay Between Sends*\n\n"
        "How long should the bot wait between each email send?\n"
        "_(Randomised within the chosen range to avoid spam filters.)_",
        parse_mode="Markdown",
        reply_markup=get_delay_keyboard(),
    )


# ── Step 5 – Delay ────────────────────────────────────────────────────────────

@router.callback_query(OperationStates.choosing_delay, F.data.startswith("delay:"))
async def process_delay_choice(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    if parts[1] == "custom":
        await state.set_state(OperationStates.entering_custom_delay)
        await callback.message.edit_text(
            "⚙️ *Custom Delay*\n\n"
            "Send two numbers: min and max seconds.\n"
            "Example: `20 90` means random 20–90 seconds between each send.",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard("operations"),
        )
        await callback.answer()
        return

    delay_min, delay_max = int(parts[1]), int(parts[2])
    await state.update_data(delay_min=delay_min, delay_max=delay_max)
    await _show_confirmation(callback.message, state)
    await callback.answer()


@router.message(OperationStates.entering_custom_delay)
async def process_custom_delay(message: Message, state: FSMContext):
    parts = message.text.strip().split()
    try:
        assert len(parts) == 2
        low, high = int(parts[0]), int(parts[1])
        assert 1 <= low < high <= 3600
    except (ValueError, AssertionError):
        await message.answer(
            "❌ Enter two integers, min then max (e.g. `20 90`). Max is 3600 seconds."
        )
        return
    await state.update_data(delay_min=low, delay_max=high)
    await _show_confirmation(message, state)


# ── Step 6 – Confirmation ─────────────────────────────────────────────────────

async def _show_confirmation(source, state: FSMContext):
    data = await state.get_data()
    await state.set_state(OperationStates.confirming)

    list_name, sender_emails = "?", []
    async with AsyncSessionLocal() as session:
        lst = await session.get(TargetList, data["list_id"])
        if lst:
            list_name = lst.name
            # Count targets
            count_result = await session.execute(
                select(TargetEmail).where(TargetEmail.list_id == lst.id)
            )
            target_count = len(count_result.scalars().all())

        for sid in data.get("selected_sender_ids", []):
            acc = await session.get(GmailAccount, sid)
            if acc:
                sender_emails.append(acc.email)

    total_sends = target_count * len(sender_emails)
    senders_str = "\n".join(f"  • `{e}`" for e in sender_emails)
    text = (
        f"📊 *Operation Summary*\n\n"
        f"📋 *Target list:* {list_name} ({target_count} emails)\n"
        f"✉️ *Senders ({len(sender_emails)}):*\n{senders_str}\n"
        f"📝 *Subject:* {data['subject']}\n"
        f"⏱ *Delay:* {data['delay_min']}–{data['delay_max']} seconds\n"
        f"📦 *Total sends:* {total_sends} (each target × each sender)\n\n"
        f"_Preview body:_\n```\n{data['body'][:300]}{'…' if len(data['body']) > 300 else ''}\n```\n\n"
        f"Ready to launch?"
    )

    keyboard = get_confirmation_keyboard()
    if isinstance(source, Message):
        await source.answer(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await source.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


@router.callback_query(OperationStates.confirming, F.data == "op:confirm")
async def process_confirm(callback: CallbackQuery, state: FSMContext, db_user: User):
    data = await state.get_data()
    await state.clear()

    list_id = data["list_id"]
    selected_ids: list[int] = data["selected_sender_ids"]
    subject = data["subject"]
    body = data["body"]
    delay_min = data["delay_min"]
    delay_max = data["delay_max"]

    async with AsyncSessionLocal() as session:
        # 1. Create Operation
        op = Operation(
            user_id=db_user.id,
            list_id=list_id,
            subject=subject,
            body=body,
            delay_min=delay_min,
            delay_max=delay_max,
            status="pending",
        )
        session.add(op)
        await session.commit()
        await session.refresh(op)

        # 2. Link selected senders
        for gmail_id in selected_ids:
            session.add(OperationSender(operation_id=op.id, gmail_account_id=gmail_id))

        # 3. Build send queue: one row per (target × sender)
        targets_result = await session.execute(
            select(TargetEmail).where(TargetEmail.list_id == list_id)
        )
        targets = targets_result.scalars().all()

        for target in targets:
            for gmail_id in selected_ids:
                session.add(
                    OperationSend(
                        operation_id=op.id,
                        target_email_id=target.id,
                        gmail_account_id=gmail_id,
                        status="pending",
                    )
                )

        await session.commit()
        op_id = op.id

    # 4. Launch in background
    await launch_operation(op_id)

    await callback.message.edit_text(
        "🚀 *Operation launched!*\n\n"
        "Emails are being sent in the background.\n"
        "You'll receive a notification when it's complete.",
        parse_mode="Markdown",
        reply_markup=get_operations_menu_keyboard(),
    )
    await callback.answer()
