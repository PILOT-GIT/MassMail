"""
Target list management.

A list stores plain email addresses (no first/last name required).

Adding targets
--------------
- Single email: type directly in chat
- CSV upload:   one email per line, or  email  column header
"""

import csv
import io
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards import get_cancel_keyboard, get_dynamic_selection_keyboard, get_list_menu_keyboard
from bot.states import TargetListStates
from database import AsyncSessionLocal
from models import TargetEmail, TargetList, User

router = Router()
EMAIL_REGEX = re.compile(r"^[\w.\-+]+@[\w.\-]+\.\w+$")


# ── View lists ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "list:list")
async def process_view_lists(callback: CallbackQuery, db_user: User):
    async with AsyncSessionLocal() as session:
        lists_result = await session.execute(
            select(TargetList).where(TargetList.user_id == db_user.id)
        )
        lists = lists_result.scalars().all()

        details = []
        for lst in lists:
            count_result = await session.execute(
                select(TargetEmail).where(TargetEmail.list_id == lst.id)
            )
            count = len(count_result.scalars().all())
            details.append(f"• *{lst.name}* — `{count}` emails")

    if not details:
        text = "👥 *No target lists yet.*\n\nCreate one using the menu below."
    else:
        text = "👥 *Your target lists:*\n\n" + "\n".join(details)

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=get_list_menu_keyboard())
    await callback.answer()


# ── Create new list ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "list:create")
async def process_create_list(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TargetListStates.entering_list_name)
    await callback.message.edit_text(
        "📝 *New Target List — Step 1*\n\nEnter a name for this list:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("lists"),
    )
    await callback.answer()


@router.message(TargetListStates.entering_list_name)
async def process_list_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name or len(name) > 100:
        await message.answer("❌ Name must be 1–100 characters. Try again:")
        return
    await state.update_data(list_name=name, list_id=None)
    await state.set_state(TargetListStates.choosing_add_method)
    await message.answer(
        f"✅ List name set: *{name}*\n\nNow how do you want to add target emails?",
        parse_mode="Markdown",
        reply_markup=_add_method_keyboard(),
    )


# ── Add email to existing list ────────────────────────────────────────────────

@router.callback_query(F.data == "list:add_email")
async def process_add_email_start(callback: CallbackQuery, state: FSMContext, db_user: User):
    """Pick a list, then add a single email or upload CSV."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TargetList).where(TargetList.user_id == db_user.id)
        )
        lists = result.scalars().all()

    if not lists:
        await callback.answer("No lists yet. Create one first.", show_alert=True)
        return

    options = [(lst.name, f"list_pick:{lst.id}") for lst in lists]
    await callback.message.edit_text(
        "➕ *Add emails — select a list:*",
        parse_mode="Markdown",
        reply_markup=get_dynamic_selection_keyboard(options, "lists"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("list_pick:"))
async def process_list_picked(callback: CallbackQuery, state: FSMContext):
    list_id = int(callback.data.split(":")[1])
    await state.update_data(list_id=list_id, list_name=None)
    await state.set_state(TargetListStates.choosing_add_method)
    await callback.message.edit_text(
        "How do you want to add target emails?",
        reply_markup=_add_method_keyboard(),
    )
    await callback.answer()


# ── Method selection ──────────────────────────────────────────────────────────

def _add_method_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="✏️ Type single email", callback_data="list_method:single")
    b.button(text="📂 Upload CSV", callback_data="list_method:csv")
    b.button(text="🔙 Cancel", callback_data="back:lists")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(TargetListStates.choosing_add_method, F.data == "list_method:single")
async def method_single(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TargetListStates.entering_single_email)
    await callback.message.edit_text(
        "✏️ Type the email address to add:",
        reply_markup=get_cancel_keyboard("lists"),
    )
    await callback.answer()


@router.callback_query(TargetListStates.choosing_add_method, F.data == "list_method:csv")
async def method_csv(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TargetListStates.uploading_csv)
    await callback.message.edit_text(
        "📂 *Upload CSV*\n\n"
        "Upload a `.csv` file. Accepted formats:\n"
        "• One email per line (no header)\n"
        "• Column named `email` (with or without other columns)\n\n"
        "Max 2 MB.",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard("lists"),
    )
    await callback.answer()


# ── Single email entry ────────────────────────────────────────────────────────

@router.message(TargetListStates.entering_single_email)
async def process_single_email(message: Message, state: FSMContext, db_user: User):
    email = message.text.strip().lower()
    if not EMAIL_REGEX.match(email):
        await message.answer("❌ Invalid email address. Try again:")
        return

    data = await state.get_data()
    list_id = await _ensure_list(db_user.id, data)

    added = await _upsert_email(list_id, email)
    await state.clear()
    if added:
        await message.answer(f"✅ `{email}` added to the list.", parse_mode="Markdown",
                             reply_markup=get_list_menu_keyboard())
    else:
        await message.answer(f"ℹ️ `{email}` was already in the list.", parse_mode="Markdown",
                             reply_markup=get_list_menu_keyboard())


# ── CSV upload ────────────────────────────────────────────────────────────────

@router.message(TargetListStates.uploading_csv, F.document)
async def process_csv_upload(message: Message, state: FSMContext, bot: Bot, db_user: User):
    doc = message.document
    if not doc.file_name.lower().endswith(".csv"):
        await message.answer("❌ Please upload a `.csv` file.")
        return
    if doc.file_size > 2 * 1024 * 1024:
        await message.answer("❌ File too large (max 2 MB).")
        return

    file_info = await bot.get_file(doc.file_id)
    raw = await bot.download_file(file_info.file_path)

    try:
        text_io = io.StringIO(raw.read().decode("utf-8"))
        reader = csv.reader(text_io)
        rows = list(reader)
    except Exception as exc:
        await message.answer(f"❌ Could not parse CSV: {exc}")
        return

    emails = _extract_emails(rows)
    if not emails:
        await message.answer("❌ No valid email addresses found in the file.")
        return

    data = await state.get_data()
    list_id = await _ensure_list(db_user.id, data)

    added_count = 0
    for email in emails:
        if await _upsert_email(list_id, email):
            added_count += 1

    await state.clear()
    await message.answer(
        f"✅ *Import complete.*\n\nNew emails added: `{added_count}` of `{len(emails)}`",
        parse_mode="Markdown",
        reply_markup=get_list_menu_keyboard(),
    )


def _extract_emails(rows: list[list[str]]) -> list[str]:
    """Parse emails from CSV rows. Handles 'email' header or bare list."""
    if not rows:
        return []

    header = [c.strip().lower() for c in rows[0]]
    email_col = None
    if "email" in header:
        email_col = header.index("email")
        rows = rows[1:]  # skip header

    results = []
    for row in rows:
        if not row:
            continue
        raw = row[email_col].strip() if email_col is not None else row[0].strip()
        email = raw.lower()
        if EMAIL_REGEX.match(email):
            results.append(email)

    return list(dict.fromkeys(results))  # deduplicate, preserve order


# ── Delete list ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "list:delete")
async def process_delete_list_start(callback: CallbackQuery, db_user: User):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TargetList).where(TargetList.user_id == db_user.id)
        )
        lists = result.scalars().all()

    if not lists:
        await callback.answer("No lists to delete.", show_alert=True)
        return

    options = [(lst.name, f"list_del:{lst.id}") for lst in lists]
    await callback.message.edit_text(
        "🗑 *Delete Target List*\n\nSelect the list to delete permanently:",
        parse_mode="Markdown",
        reply_markup=get_dynamic_selection_keyboard(options, "lists"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("list_del:"))
async def process_delete_list_confirm(callback: CallbackQuery, db_user: User):
    list_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        lst = await session.get(TargetList, list_id)
        if lst and lst.user_id == db_user.id:
            name = lst.name
            await session.delete(lst)
            await session.commit()
            await callback.message.edit_text(
                f"✅ List *{name}* deleted.", parse_mode="Markdown",
                reply_markup=get_list_menu_keyboard(),
            )
        else:
            await callback.answer("List not found.", show_alert=True)
    await callback.answer()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _ensure_list(user_id: int, state_data: dict) -> int:
    """Return existing list_id or create a new one using the saved name."""
    list_id = state_data.get("list_id")
    if list_id:
        return list_id

    name = state_data.get("list_name", "Untitled List")
    async with AsyncSessionLocal() as session:
        new_list = TargetList(user_id=user_id, name=name)
        session.add(new_list)
        await session.commit()
        await session.refresh(new_list)
        return new_list.id


async def _upsert_email(list_id: int, email: str) -> bool:
    """Insert email if not present. Returns True if inserted, False if already existed."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TargetEmail).where(
                TargetEmail.list_id == list_id, TargetEmail.email == email
            )
        )
        if result.scalar_one_or_none():
            return False
        session.add(TargetEmail(list_id=list_id, email=email))
        await session.commit()
        return True
