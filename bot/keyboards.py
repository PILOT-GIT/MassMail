from typing import List, Set, Tuple

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── Main menu ────────────────────────────────────────────────────────────────

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📧 Operations", callback_data="menu:operations")
    b.button(text="👥 Target Lists", callback_data="menu:lists")
    b.button(text="✉️ Gmail Accounts", callback_data="menu:gmail")
    b.button(text="🔐 User Management", callback_data="menu:auth")
    b.adjust(2, 2)
    return b.as_markup()


# ── Operations ───────────────────────────────────────────────────────────────

def get_operations_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ New Operation", callback_data="op:create")
    b.button(text="📜 View Operations", callback_data="op:list")
    b.button(text="🔙 Main Menu", callback_data="back:main")
    b.adjust(1)
    return b.as_markup()


# ── Gmail accounts ───────────────────────────────────────────────────────────

def get_gmail_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Add Single Account", callback_data="gmail:add_single")
    b.button(text="📂 Import from CSV", callback_data="gmail:add_csv")
    b.button(text="📜 View Accounts", callback_data="gmail:list")
    b.button(text="🗑 Remove Account", callback_data="gmail:remove")
    b.button(text="🔙 Main Menu", callback_data="back:main")
    b.adjust(2, 2, 1)
    return b.as_markup()


# ── Target lists ─────────────────────────────────────────────────────────────

def get_list_menu_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ New List", callback_data="list:create")
    b.button(text="📜 View Lists", callback_data="list:list")
    b.button(text="➕ Add Email to List", callback_data="list:add_email")
    b.button(text="🗑 Delete List", callback_data="list:delete")
    b.button(text="🔙 Main Menu", callback_data="back:main")
    b.adjust(2, 2, 1)
    return b.as_markup()


# ── Auth / user management ───────────────────────────────────────────────────

def get_auth_menu_keyboard(is_owner: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="➕ Add User", callback_data="auth:add_user")
    b.button(text="🗑 Remove User", callback_data="auth:remove_user")
    if is_owner:
        b.button(text="⬆️ Make Admin", callback_data="auth:make_admin")
        b.button(text="⬇️ Remove Admin", callback_data="auth:remove_admin")
    b.button(text="👥 List Users", callback_data="auth:list_users")
    b.button(text="🔙 Main Menu", callback_data="back:main")
    b.adjust(2, 2, 1, 1) if is_owner else b.adjust(2, 1, 1)
    return b.as_markup()


# ── Dynamic single-select ────────────────────────────────────────────────────

def get_dynamic_selection_keyboard(
    options: List[Tuple[str, str]], back_target: str
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for label, cb in options:
        b.button(text=label, callback_data=cb)
    b.button(text="🔙 Cancel", callback_data=f"back:{back_target}")
    b.adjust(1)
    return b.as_markup()


# ── Multi-select sender keyboard ─────────────────────────────────────────────

def get_sender_selection_keyboard(
    accounts: list,  # list of GmailAccount objects
    selected_ids: Set[int],
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for acc in accounts:
        tick = "☑️" if acc.id in selected_ids else "☐"
        b.button(text=f"{tick} {acc.email}", callback_data=f"toggle_sender:{acc.id}")
    count = len(selected_ids)
    confirm_label = f"✅ Confirm ({count} selected)" if count else "✅ Confirm (select at least 1)"
    b.button(text=confirm_label, callback_data="confirm_senders")
    b.button(text="🔙 Cancel", callback_data="back:operations")
    b.adjust(1)
    return b.as_markup()


# ── Delay presets ────────────────────────────────────────────────────────────

def get_delay_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⚡ Fast  (10–30 s)", callback_data="delay:10:30")
    b.button(text="🕐 Normal (30–120 s)", callback_data="delay:30:120")
    b.button(text="🐢 Slow  (120–300 s)", callback_data="delay:120:300")
    b.button(text="⚙️ Custom…", callback_data="delay:custom")
    b.button(text="🔙 Cancel", callback_data="back:operations")
    b.adjust(1)
    return b.as_markup()


# ── Confirmation ─────────────────────────────────────────────────────────────

def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🚀 Launch Operation", callback_data="op:confirm")
    b.button(text="❌ Cancel", callback_data="back:operations")
    b.adjust(1)
    return b.as_markup()


# ── Generic cancel ───────────────────────────────────────────────────────────

def get_cancel_keyboard(back_target: str = "main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Cancel", callback_data=f"back:{back_target}")
    return b.as_markup()
