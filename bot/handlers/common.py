from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    get_gmail_menu_keyboard,
    get_list_menu_keyboard,
    get_main_menu_keyboard,
    get_operations_menu_keyboard,
    get_auth_menu_keyboard,
)
from models import User

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User):
    name = f"@{db_user.telegram_username}" if db_user.telegram_username else "there"
    await message.answer(
        f"👋 Hello, {name}!\n\nWelcome to the *Mass Mailer Bot*. Use the menu below.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "🎛 *Main Menu*",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )


@router.callback_query(F.data == "back:main")
@router.callback_query(F.data == "cancel")
async def handle_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🎛 *Main Menu*",
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("menu:"))
async def handle_menu_nav(callback: CallbackQuery, db_user: User):
    section = callback.data.split(":")[1]

    if section == "operations":
        await callback.message.edit_text(
            "📧 *Operations*\n\nCreate and track your mail operations.",
            parse_mode="Markdown",
            reply_markup=get_operations_menu_keyboard(),
        )
    elif section == "lists":
        await callback.message.edit_text(
            "👥 *Target Lists*\n\nManage your email target lists.",
            parse_mode="Markdown",
            reply_markup=get_list_menu_keyboard(),
        )
    elif section == "gmail":
        await callback.message.edit_text(
            "✉️ *Gmail Accounts*\n\nManage your sender accounts.",
            parse_mode="Markdown",
            reply_markup=get_gmail_menu_keyboard(),
        )
    elif section == "auth":
        if not db_user.is_admin_or_above:
            await callback.answer("Admin access required.", show_alert=True)
            return
        await callback.message.edit_text(
            "🔐 *User Management*",
            parse_mode="Markdown",
            reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
        )

    await callback.answer()


@router.callback_query(F.data.startswith("back:"))
async def handle_back(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    target = callback.data.split(":")[1]

    if target == "operations":
        await callback.message.edit_text(
            "📧 *Operations*",
            parse_mode="Markdown",
            reply_markup=get_operations_menu_keyboard(),
        )
    elif target == "lists":
        await callback.message.edit_text(
            "👥 *Target Lists*",
            parse_mode="Markdown",
            reply_markup=get_list_menu_keyboard(),
        )
    elif target == "gmail":
        await callback.message.edit_text(
            "✉️ *Gmail Accounts*",
            parse_mode="Markdown",
            reply_markup=get_gmail_menu_keyboard(),
        )
    elif target == "auth":
        await callback.message.edit_text(
            "🔐 *User Management*",
            parse_mode="Markdown",
            reply_markup=get_auth_menu_keyboard(is_owner=db_user.is_owner),
        )
    else:
        await callback.message.edit_text(
            "🎛 *Main Menu*",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard(),
        )
    await callback.answer()
