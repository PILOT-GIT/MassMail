"""
User management for the bot.

Commands (all via Telegram message):
  /users            – list all authorized users  (admin+)
  /adduser <id>     – authorize a user            (admin+)
  /removeuser <id>  – deauthorize a user          (admin+)
  /makeadmin <id>   – promote user to admin       (owner only)
  /removeadmin <id> – demote admin to user        (owner only)

Also handles the 'User Management' inline menu.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from bot.keyboards import get_auth_menu_keyboard, get_main_menu_keyboard
from config import settings
from database import AsyncSessionLocal
from models import User

router = Router()


# ── Inline menu ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:auth")
async def show_auth_menu(callback: CallbackQuery, db_user: User):
    if not db_user.is_admin_or_above:
        await callback.answer("Admin access required.", show_alert=True)
        return
    await callback.message.edit_text(
        "🔐 *User Management*\n\nManage who can access this bot.",
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
    )
    await callback.answer()


# ── List users ───────────────────────────────────────────────────────────────

async def _list_users_text() -> str:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.role != "unauthorized").order_by(User.role)
        )
        users = result.scalars().all()

    if not users:
        return "No authorized users yet."

    owners = []
    admins = []
    regular_users = []

    for u in users:
        if u.role == "owner":
            owners.append(u)
        elif u.role == "admin":
            admins.append(u)
        elif u.role == "user":
            regular_users.append(u)

    segments = []
    if owners:
        lines = []
        for u in owners:
            link_text = f"@{u.telegram_username}" if u.telegram_username else "Unknown User"
            lines.append(f"• [{link_text}](tg://user?id={u.telegram_id}) — `{u.telegram_id}` — *{u.role}*")
        segments.append("👑 *Owners*\n" + "\n".join(lines))

    if admins:
        lines = []
        for u in admins:
            link_text = f"@{u.telegram_username}" if u.telegram_username else "Unknown User"
            lines.append(f"• [{link_text}](tg://user?id={u.telegram_id}) — `{u.telegram_id}` — *{u.role}*")
        segments.append("🛡 *Admins*\n" + "\n".join(lines))

    if regular_users:
        lines = []
        for u in regular_users:
            link_text = f"@{u.telegram_username}" if u.telegram_username else "Unknown User"
            lines.append(f"• [{link_text}](tg://user?id={u.telegram_id}) — `{u.telegram_id}` — *{u.role}*")
        segments.append("👥 *Users*\n" + "\n".join(lines))

    if not segments:
        return "No authorized users yet."

    return "\n\n".join(segments)


@router.callback_query(F.data == "auth:list_users")
async def cb_list_users(callback: CallbackQuery, db_user: User):
    if not db_user.is_admin_or_above:
        await callback.answer("Admin access required.", show_alert=True)
        return
    text = await _list_users_text()
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
    )
    await callback.answer()


@router.message(Command("users"))
async def cmd_list_users(message: Message, db_user: User):
    if not db_user.is_admin_or_above:
        await message.answer("⛔ Admin access required.")
        return
    text = await _list_users_text()
    await message.answer(text, parse_mode="Markdown")


# ── Generic helper ───────────────────────────────────────────────────────────

async def _get_target(raw_id: str) -> User | None:
    try:
        tg_id = int(raw_id.strip())
    except ValueError:
        return None
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        return result.scalar_one_or_none()


def _parse_id(message: Message, command: str) -> str | None:
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    return parts[1].strip()


# ── Add user ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "auth:add_user")
async def cb_add_user_prompt(callback: CallbackQuery, db_user: User):
    if not db_user.is_admin_or_above:
        await callback.answer("Admin access required.", show_alert=True)
        return
    await callback.message.edit_text(
        "➕ *Add User*\n\nSend the Telegram ID of the person to authorize:\n`/adduser <telegram_id>`",
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
    )
    await callback.answer()


@router.message(Command("adduser"))
async def cmd_add_user(message: Message, db_user: User):
    if not db_user.is_admin_or_above:
        await message.answer("⛔ Admin access required.")
        return

    raw = _parse_id(message, "adduser")
    if not raw:
        await message.answer("Usage: `/adduser <telegram_id>`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(raw)
        except ValueError:
            await message.answer("❌ Invalid Telegram ID.")
            return

        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        target = result.scalar_one_or_none()

        if target:
            if target.role in ("owner", "admin") and not db_user.is_owner:
                await message.answer("❌ You cannot modify an admin or owner.")
                return
            target.role = "user"
        else:
            target = User(telegram_id=tg_id, role="user")
            session.add(target)

        await session.commit()

    await message.answer(f"✅ User `{tg_id}` has been authorized.", parse_mode="Markdown")


# ── Remove user ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "auth:remove_user")
async def cb_remove_user_prompt(callback: CallbackQuery, db_user: User):
    if not db_user.is_admin_or_above:
        await callback.answer("Admin access required.", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 *Remove User*\n\nSend the Telegram ID to deauthorize:\n`/removeuser <telegram_id>`",
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
    )
    await callback.answer()


@router.message(Command("removeuser"))
async def cmd_remove_user(message: Message, db_user: User):
    if not db_user.is_admin_or_above:
        await message.answer("⛔ Admin access required.")
        return

    raw = _parse_id(message, "removeuser")
    if not raw:
        await message.answer("Usage: `/removeuser <telegram_id>`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(raw)
        except ValueError:
            await message.answer("❌ Invalid Telegram ID.")
            return

        if tg_id == db_user.telegram_id:
            await message.answer("❌ You cannot remove yourself.")
            return

        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        target = result.scalar_one_or_none()

        if not target:
            await message.answer("❌ User not found.")
            return

        if target.role == "owner":
            await message.answer("❌ Cannot remove the owner.")
            return

        if target.role == "admin" and not db_user.is_owner:
            await message.answer("❌ Only the owner can remove admins.")
            return

        target.role = "unauthorized"
        await session.commit()

    await message.answer(f"✅ User `{tg_id}` has been deauthorized.", parse_mode="Markdown")


# ── Make admin (owner only) ───────────────────────────────────────────────────

@router.callback_query(F.data == "auth:make_admin")
async def cb_make_admin_prompt(callback: CallbackQuery, db_user: User):
    if not db_user.is_owner:
        await callback.answer("Owner access required.", show_alert=True)
        return
    await callback.message.edit_text(
        "⬆️ *Make Admin*\n\nSend the Telegram ID to promote:\n`/makeadmin <telegram_id>`",
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=True),
    )
    await callback.answer()


@router.message(Command("makeadmin"))
async def cmd_make_admin(message: Message, db_user: User):
    if not db_user.is_owner:
        await message.answer("⛔ Owner access required.")
        return

    raw = _parse_id(message, "makeadmin")
    if not raw:
        await message.answer("Usage: `/makeadmin <telegram_id>`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(raw)
        except ValueError:
            await message.answer("❌ Invalid Telegram ID.")
            return

        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        target = result.scalar_one_or_none()

        if not target:
            target = User(telegram_id=tg_id, role="admin")
            session.add(target)
        else:
            if target.role == "owner":
                await message.answer("❌ Cannot change the owner's role.")
                return
            target.role = "admin"
        await session.commit()

    await message.answer(f"✅ User `{tg_id}` is now an admin.", parse_mode="Markdown")


# ── Remove admin (owner only) ─────────────────────────────────────────────────

@router.callback_query(F.data == "auth:remove_admin")
async def cb_remove_admin_prompt(callback: CallbackQuery, db_user: User):
    if not db_user.is_owner:
        await callback.answer("Owner access required.", show_alert=True)
        return
    await callback.message.edit_text(
        "⬇️ *Remove Admin*\n\nSend the Telegram ID to demote:\n`/removeadmin <telegram_id>`",
        parse_mode="Markdown",
        reply_markup=get_auth_menu_keyboard(is_owner=True),
    )
    await callback.answer()


@router.message(Command("removeadmin"))
async def cmd_remove_admin(message: Message, db_user: User):
    if not db_user.is_owner:
        await message.answer("⛔ Owner access required.")
        return

    raw = _parse_id(message, "removeadmin")
    if not raw:
        await message.answer("Usage: `/removeadmin <telegram_id>`", parse_mode="Markdown")
        return

    async with AsyncSessionLocal() as session:
        try:
            tg_id = int(raw)
        except ValueError:
            await message.answer("❌ Invalid Telegram ID.")
            return

        result = await session.execute(select(User).where(User.telegram_id == tg_id))
        target = result.scalar_one_or_none()

        if not target or target.role != "admin":
            await message.answer("❌ That user is not an admin.")
            return

        target.role = "user"
        await session.commit()

    await message.answer(f"✅ User `{tg_id}` demoted to regular user.", parse_mode="Markdown")


# ── Access Requests & Approvals ──────────────────────────────────────────────

@router.message(Command("request"))
async def cmd_request_access(message: Message):
    telegram_id = message.from_user.id
    username = message.from_user.username
    user_display = f"@{username}" if username else "no username"
    
    # 1. Check if the user is already authorized
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        db_user = result.scalar_one_or_none()
        
    if db_user and db_user.is_authorized:
        await message.answer("✅ You are already authorized to use this bot.")
        return

    # 2. Build explicit payload & inline buttons
    payload = (
        f"🔔 New access request\n\n"
        f"User: {user_display}\n"
        f"Telegram ID: `{telegram_id}`\n\n"
        f"Approve or deny below."
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_request:{telegram_id}"),
                InlineKeyboardButton(text="❌ Deny", callback_data=f"deny_request:{telegram_id}"),
            ]
        ]
    )

    # 3. Direct to settings.OWNER_TELEGRAM_ID
    try:
        await message.bot.send_message(
            chat_id=settings.OWNER_TELEGRAM_ID,
            text=payload,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await message.answer("🔔 Request sent. You will be notified once the owner reviews it.")
    except Exception as exc:
        # Notify the requester if the owner's chat cannot be resolved
        await message.answer("❌ Could not send access request to the owner. Please ensure the owner has started the bot.")


@router.callback_query(F.data.startswith("approve_request:") | F.data.startswith("deny_request:"))
async def process_owner_callback(callback: CallbackQuery):
    # Only the owner can approve or deny access requests
    if callback.from_user.id != settings.OWNER_TELEGRAM_ID:
        await callback.answer("Only the owner can approve or deny requests.", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[0]
    target_telegram_id = int(parts[1])

    # Extract username from original message text
    username = "Unknown User"
    if callback.message and callback.message.text:
        lines = callback.message.text.split("\n")
        for line in lines:
            if line.startswith("User:"):
                username = line.replace("User:", "").strip()
                break

    if action == "approve_request":
        # Upsert user into the DB with the role "user"
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == target_telegram_id)
            )
            db_user = result.scalar_one_or_none()
            
            clean_username = username
            if clean_username.startswith("@"):
                clean_username = clean_username[1:]
            if clean_username in ("no username", "Unknown User"):
                clean_username = None

            if db_user:
                db_user.role = "user"
                if clean_username:
                    db_user.telegram_username = clean_username
            else:
                db_user = User(
                    telegram_id=target_telegram_id,
                    telegram_username=clean_username,
                    role="user",
                )
                session.add(db_user)
            await session.commit()

        # Alert user
        try:
            await callback.bot.send_message(
                chat_id=target_telegram_id,
                text="✅ Your access request has been approved! Use /start to begin."
            )
        except Exception:
            pass

        # Mutate the original message to: "✅ Approved: @username (`id`)"
        await callback.message.edit_text(
            text=f"✅ Approved: {username} (`{target_telegram_id}`)",
            parse_mode="Markdown",
        )
        await callback.answer("Request approved.")

    elif action == "deny_request":
        # Notify the user
        try:
            await callback.bot.send_message(
                chat_id=target_telegram_id,
                text="❌ Your access request was denied."
            )
        except Exception:
            pass

        # Mutate the original message to: "❌ Denied: @username (`id`)"
        await callback.message.edit_text(
            text=f"❌ Denied: {username} (`{target_telegram_id}`)",
            parse_mode="Markdown",
        )
        await callback.answer("Request denied.")
