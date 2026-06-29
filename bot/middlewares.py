from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from config import settings
from database import AsyncSessionLocal
from models import User


class AuthMiddleware(BaseMiddleware):
    """
    Role-based authorization middleware.

    - If the sender is the configured OWNER_TELEGRAM_ID, they are
      automatically given the 'owner' role (even on first contact).
    - Authorized roles (owner / admin / user) are passed through.
    - Unauthorized users receive a one-time denial message showing their
      Telegram ID so they can pass it to an admin.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # ── Determine who is acting ──────────────────────────────────────────
        if not hasattr(event, "from_user") or event.from_user is None:
            return await handler(event, data)

        tg_id = event.from_user.id
        tg_username = event.from_user.username

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()

            # ── Auto-create / promote owner ──────────────────────────────────
            if tg_id == settings.OWNER_TELEGRAM_ID:
                if not user:
                    user = User(
                        telegram_id=tg_id,
                        telegram_username=tg_username,
                        role="owner",
                    )
                    session.add(user)
                else:
                    user.role = "owner"
                    if tg_username:
                        user.telegram_username = tg_username
                await session.commit()
                await session.refresh(user)

            elif not user:
                # Just create a transient User object without saving to DB
                user = User(
                    telegram_id=tg_id,
                    telegram_username=tg_username,
                    role="unauthorized",
                )

            # ── Gate unauthorized users ──────────────────────────────────────
            is_request_command = False
            if isinstance(event, Message) and event.text:
                text = event.text.strip()
                if text == "/request" or text.startswith("/request "):
                    is_request_command = True

            if not user.is_authorized and not is_request_command:
                denial = (
                    "⛔ You are not authorized.\n\n"
                    "Send /request to request access from the owner."
                )
                if isinstance(event, Message):
                    await event.answer(denial)
                elif isinstance(event, CallbackQuery):
                    await event.answer("Access denied.", show_alert=True)
                return

            # ── Inject user into handler context ─────────────────────────────
            data["db_user"] = user
            data["db_session"] = session
            return await handler(event, data)
