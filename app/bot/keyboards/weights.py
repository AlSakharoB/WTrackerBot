from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import WEIGHT_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.goals import GOAL_MENU
from app.services.weights import WeightPage
from app.utils.decimal import format_decimal
from app.utils.formatting import format_datetime

WEIGHT_ADD = "weight:add"
WEIGHT_CHART = "weight:chart"
WEIGHT_HISTORY = "weight:history"
WEIGHT_MENU = "weight:menu"
WEIGHT_BACK_MAIN = "weight:back_main"
WEIGHT_CANCEL = "weight:cancel"
WEIGHT_NOOP = "weight:noop"


class WeightTimeCallback(CallbackData, prefix="wtime"):
    action: str


class WeightPageCallback(CallbackData, prefix="wpage"):
    page: int


class WeightEntryCallback(CallbackData, prefix="wentry"):
    action: str
    entry_id: int
    page: int


def build_weight_menu_keyboard(has_entries: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ Добавить вес", callback_data=WEIGHT_ADD)]]
    if has_entries:
        rows.append(
            [InlineKeyboardButton(text="📋 История", callback_data=WEIGHT_HISTORY)]
        )
        rows.append(
            [InlineKeyboardButton(text="📈 График", callback_data=WEIGHT_CHART)]
        )
    rows.append([InlineKeyboardButton(text="🎯 Цели", callback_data=GOAL_MENU)])
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Главное меню",
                callback_data=WEIGHT_BACK_MAIN,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_time_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕒 Сейчас",
                    callback_data=WeightTimeCallback(action="now").pack(),
                ),
                InlineKeyboardButton(
                    text="🌅 Сегодня утром",
                    callback_data=WeightTimeCallback(action="morning").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📆 Указать дату и время",
                    callback_data=WeightTimeCallback(action="custom").pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=WEIGHT_CANCEL)],
        ]
    )


def build_weight_save_keyboard(action_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data=ConfirmActionCallback(
                        action=WEIGHT_SAVE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=WEIGHT_CANCEL)],
        ]
    )


def build_weight_history_keyboard(
    page: WeightPage,
    timezone_name: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in page.items:
        measured_at = format_datetime(entry.measured_at, timezone_name).split()[0]
        builder.row(
            InlineKeyboardButton(
                text=f"{measured_at} — {format_decimal(entry.weight_kg)} кг",
                callback_data=WeightEntryCallback(
                    action="view",
                    entry_id=entry.id,
                    page=page.page,
                ).pack(),
            )
        )
    if page.pages > 1:
        previous = (
            WeightPageCallback(page=page.page - 1).pack()
            if page.page > 1
            else WEIGHT_NOOP
        )
        following = (
            WeightPageCallback(page=page.page + 1).pack()
            if page.page < page.pages
            else WEIGHT_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=WEIGHT_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    builder.row(InlineKeyboardButton(text="⬅️ К весу", callback_data=WEIGHT_MENU))
    return builder.as_markup()


def build_weight_entry_keyboard(entry_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить вес",
                    callback_data=WeightEntryCallback(
                        action="edit_weight",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🕒 Изменить время",
                    callback_data=WeightEntryCallback(
                        action="edit_time",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=WeightEntryCallback(
                        action="delete",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К истории",
                    callback_data=WeightPageCallback(page=page).pack(),
                )
            ],
        ]
    )


def build_weight_delete_keyboard(entry_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=WeightEntryCallback(
                        action="delete_confirm",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=WeightEntryCallback(
                        action="view",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_weight_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=WEIGHT_CANCEL)]
        ]
    )
