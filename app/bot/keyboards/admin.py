from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class AdminAction(StrEnum):
    MENU = "menu"
    HEALTH = "health"
    USERS = "users"
    STATS = "stats"
    DATABASE = "database"
    VERSION = "version"
    ERRORS = "errors"
    CLOSE = "close"


class AdminCallback(CallbackData, prefix="adm"):
    action: AdminAction


def _button(text: str, action: AdminAction) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=AdminCallback(action=action).pack(),
    )


def build_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🟢 Состояние системы", AdminAction.HEALTH)],
            [_button("👥 Пользователи", AdminAction.USERS)],
            [_button("📊 Статистика", AdminAction.STATS)],
            [_button("🗄 База данных", AdminAction.DATABASE)],
            [_button("⚙️ Версия приложения", AdminAction.VERSION)],
            [_button("❗ Ошибки", AdminAction.ERRORS)],
            [_button("⬅️ Закрыть", AdminAction.CLOSE)],
        ]
    )


def build_admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("⬅️ Назад", AdminAction.MENU)]]
    )
