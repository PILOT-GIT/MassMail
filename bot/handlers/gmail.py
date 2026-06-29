"""
Gmail account management.

Add methods
-----------
- One-by-one: user enters email, then app password
- CSV import: upload a file with columns  email,password
  (headers are optional; first column = email, second = password)
"""

import asyncio
import csv
import io
import json
import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards import get_cancel_keyboard, get_dynamic_selection_keyboard, get_gmail_menu_keyboard
from bot.states import GmailAuthStates
from database import AsyncSessionLocal
from encryption import encryptor
from gmail_service import test_smtp_credentials
from models import GmailAccount, User

logger = logging.getLogger(__name__)
router = Router()

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# ── View accounts ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "gmail:list")
async def process_list_accounts(callback: CallbackQuery, db_user: User):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GmailAccount).where(GmailAccount.user_id == db_user.id)
        )
        accounts = result.scalars().all()

    if not accounts:
        text = "✉️ *No Gmail accounts added yet.*\n\nUse the menu below to add one."
    else:
        lines = [f"• `{acc.email}`" for acc in accounts]
        text = "✉️ *Connected Gmail accounts:*\n\n" + "\n".join(lines)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_gmail_menu_keyboard())
    await callback.answer()


# ── Add single account ────────────────────────────────────────────────────────

@router.callback_query(F.data == "gmail:add_single")
async def process_add_single_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GmailAuthStates.email_input)
    await callback.message.edit_text(
        "✉️ *Add Gmail Account — Step 1*\n\nEnter your Gmail address:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("gmail"),
    )
    await callback.answer()


@router.message(GmailAuthStates.email_input)
async def process_email_input(message: Message, state: FSMContext):
    email = message.text.strip().lower()
    if not EMAIL_REGEX.match(email):
        await message.answer("❌ Invalid email format. Try again:")
        return
    await state.update_data(email=email)
    await state.set_state(GmailAuthStates.password_input)
    await message.answer(
        "🔑 *Step 2 — App Password*\n\n"
        "Enter the 16-character Gmail App Password.\n"
        "_(Google Account → Security → App Passwords)_",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("gmail"),
    )


@router.message(GmailAuthStates.password_input)
async def process_password_input(message: Message, state: FSMContext, db_user: User):
    password = message.text.replace(" ", "").strip()
    if len(password) != 16:
        await message.answer("❌ App Passwords are exactly 16 characters. Try again:")
        return

    data = await state.get_data()
    email = data["email"]

    status_msg = await message.answer("🔄 Verifying credentials via SMTP…")
    ok = await asyncio.to_thread(test_smtp_credentials, email, password)

    if not ok:
        await status_msg.delete()
        await message.answer(
            "❌ *SMTP authentication failed.*\n\n"
            "Check that 2FA is enabled and the App Password is correct.",
            parse_mode="Markdown",
        )
        return

    await _save_account(db_user.id, email, password)
    await state.clear()
    await status_msg.delete()
    await message.answer(
        f"✅ *Account added:* `{email}`",
        parse_mode="Markdown",
        reply_markup=get_gmail_menu_keyboard(),
    )


# ── Add accounts via CSV ──────────────────────────────────────────────────────

@router.callback_query(F.data == "gmail:add_csv")
async def process_add_csv_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GmailAuthStates.csv_upload)
    await callback.message.edit_text(
        "📂 *Import Gmail accounts from CSV*\n\n"
        "Upload a `.csv` file with two columns:\n"
        "`email,password`\n\n"
        "Header row is optional. Each row = one Gmail account.\n"
        "Each password is verified via SMTP before saving.",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("gmail"),
    )
    await callback.answer()


@router.message(GmailAuthStates.csv_upload, F.document)
async def process_csv_upload(message: Message, state: FSMContext, bot: Bot, db_user: User):
    doc = message.document
    if not doc.file_name.lower().endswith(".csv"):
        await message.answer("❌ Please upload a `.csv` file.")
        return
    if doc.file_size > 2 * 1024 * 1024:
        await message.answer("❌ File too large (max 2 MB).")
        return

    file_info = await bot.get_file(doc.file_id)
    raw_bytes = await bot.download_file(file_info.file_path)

    try:
        text_io = io.StringIO(raw_bytes.read().decode("utf-8"))
        reader = csv.reader(text_io)
        rows = list(reader)
    except Exception as exc:
        await message.answer(f"❌ Could not parse CSV: {exc}")
        return

    # Strip optional header row
    if rows and rows[0] and rows[0][0].strip().lower() in ("email", "e-mail"):
        rows = rows[1:]

    if not rows:
        await message.answer("❌ No data rows found in the CSV.")
        return

    status_msg = await message.answer(f"🔄 Verifying {len(rows)} account(s)… this may take a moment.")
    added, failed = [], []

    for row in rows:
        if len(row) < 2:
            continue
        email = row[0].strip().lower()
        password = row[1].strip().replace(" ", "")
        if not EMAIL_REGEX.match(email) or len(password) != 16:
            failed.append(email or f"row_{rows.index(row)+1}")
            continue

        ok = await asyncio.to_thread(test_smtp_credentials, email, password)
        if ok:
            await _save_account(db_user.id, email, password)
            added.append(email)
        else:
            failed.append(email)

    await state.clear()
    await status_msg.delete()

    summary = f"✅ *Import complete.*\n\nAdded: `{len(added)}`\nFailed / skipped: `{len(failed)}`"
    if failed:
        summary += "\n\n*Failed:*\n" + "\n".join(f"• `{e}`" for e in failed[:20])
        if len(failed) > 20:
            summary += f"\n…and {len(failed) - 20} more."

    await message.answer(summary, parse_mode="Markdown", reply_markup=get_gmail_menu_keyboard())


# ── Remove account ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "gmail:remove")
async def process_remove_start(callback: CallbackQuery, db_user: User):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GmailAccount).where(GmailAccount.user_id == db_user.id)
        )
        accounts = result.scalars().all()

    if not accounts:
        await callback.answer("No accounts to remove.", show_alert=True)
        return

    options = [(acc.email, f"gmail_del:{acc.id}") for acc in accounts]
    await callback.message.edit_text(
        "🗑 *Remove Account*\n\nSelect the account to delete:",
        parse_mode="Markdown",
        reply_markup=get_dynamic_selection_keyboard(options, "gmail"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("gmail_del:"))
async def process_remove_confirm(callback: CallbackQuery, db_user: User):
    account_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        acc = await session.get(GmailAccount, account_id)
        if acc and acc.user_id == db_user.id:
            email = acc.email
            await session.delete(acc)
            await session.commit()
            await callback.message.edit_text(
                f"✅ Account `{email}` removed.",
                parse_mode="Markdown",
                reply_markup=get_gmail_menu_keyboard(),
            )
        else:
            await callback.answer("Account not found.", show_alert=True)
    await callback.answer()


# ── Internal helper ───────────────────────────────────────────────────────────

async def _save_account(user_id: int, email: str, password: str) -> None:
    payload = json.dumps({"app_password": password})
    encrypted = encryptor.encrypt_token(payload)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(GmailAccount).where(
                GmailAccount.user_id == user_id, GmailAccount.email == email
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.encrypted_credentials = encrypted
        else:
            session.add(GmailAccount(user_id=user_id, email=email, encrypted_credentials=encrypted))
        await session.commit()
