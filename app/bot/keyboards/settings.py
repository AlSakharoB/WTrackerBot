from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.actions import (
    NUTRITION_GOAL_TODAY_ACTION,
    NUTRITION_GOAL_TOMORROW_ACTION,
    ConfirmActionCallback,
)
from app.services.settings import POPULAR_TIMEZONES
from app.user_settings import AfterFoodAddAction, NumberFormat

SETTINGS_MENU = "settings:menu"
SETTINGS_TIMEZONE = "settings:timezone"
SETTINGS_DISPLAY = "settings:display"
SETTINGS_DIARY = "settings:diary"
SETTINGS_PRIVACY = "settings:privacy"
SETTINGS_MY_DATA = "settings:my_data"
SETTINGS_DELETE = "settings:delete"
SETTINGS_DELETE_CONTINUE = "settings:delete_continue"
SETTINGS_ABOUT = "settings:about"
SETTINGS_HELP = "settings:help"
SETTINGS_BACK_MAIN = "settings:back_main"
SETTINGS_NUTRITION_GOALS = "settings:nutrition_goals"
SETTINGS_REMINDERS = "settings:reminders"
NUTRITION_GOAL_CREATE = "nutrition_goal:create"
NUTRITION_GOAL_CANCEL = "nutrition_goal:cancel"


class TimezoneCallback(CallbackData, prefix="stz"):
    timezone: str


class NumberFormatCallback(CallbackData, prefix="snf"):
    value: NumberFormat


class AfterFoodAddCallback(CallbackData, prefix="sfa"):
    value: AfterFoodAddAction


class NutritionGoalSkipCallback(CallbackData, prefix="ngskip"):
    field: str


class NutritionGoalActionCallback(CallbackData, prefix="ngact"):
    action: str
    goal_id: int


def build_settings_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕒 Часовой пояс", callback_data=SETTINGS_TIMEZONE
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎛 Отображение", callback_data=SETTINGS_DISPLAY
                )
            ],
            [
                InlineKeyboardButton(
                    text="📅 Поведение дневника", callback_data=SETTINGS_DIARY
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Цели КБЖУ",
                    callback_data=SETTINGS_NUTRITION_GOALS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Напоминания",
                    callback_data=SETTINGS_REMINDERS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔐 Данные и приватность",
                    callback_data=SETTINGS_PRIVACY,
                )
            ],
            [InlineKeyboardButton(text="ℹ️ О боте", callback_data=SETTINGS_ABOUT)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_BACK_MAIN)],
        ]
    )


def build_timezone_keyboard(current: str) -> InlineKeyboardMarkup:
    rows = []
    for timezone in POPULAR_TIMEZONES:
        marker = "✓ " if timezone == current else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{timezone}",
                    callback_data=TimezoneCallback(timezone=timezone).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_number_format_keyboard(current: NumberFormat) -> InlineKeyboardMarkup:
    labels = {
        NumberFormat.AUTOMATIC: "Автоматически",
        NumberFormat.ONE_DECIMAL: "1 знак",
        NumberFormat.TWO_DECIMALS: "2 знака",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✓ ' if value == current else ''}{label}",
                callback_data=NumberFormatCallback(value=value).pack(),
            )
        ]
        for value, label in labels.items()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_diary_behavior_keyboard(
    current: AfterFoodAddAction,
) -> InlineKeyboardMarkup:
    labels = {
        AfterFoodAddAction.OPEN_TODAY: "Открыть «Сегодня»",
        AfterFoodAddAction.STAY: "Остаться в текущем разделе",
    }
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✓ ' if value == current else ''}{label}",
                callback_data=AfterFoodAddCallback(value=value).pack(),
            )
        ]
        for value, label in labels.items()
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_nutrition_goal_menu_keyboard(
    goal_id: int | None,
) -> InlineKeyboardMarkup:
    label = "✏️ Изменить цели" if goal_id is not None else "➕ Настроить цели"
    rows = [[InlineKeyboardButton(text=label, callback_data=NUTRITION_GOAL_CREATE)]]
    if goal_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚫 Отключить цели КБЖУ",
                    callback_data=NutritionGoalActionCallback(
                        action="disable",
                        goal_id=goal_id,
                    ).pack(),
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_nutrition_goal_input_keyboard(field: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Не задавать",
                    callback_data=NutritionGoalSkipCallback(field=field).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=NUTRITION_GOAL_CANCEL,
                )
            ],
        ]
    )


def build_nutrition_goal_date_keyboard(
    action_token: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Сегодня",
                    callback_data=ConfirmActionCallback(
                        action=NUTRITION_GOAL_TODAY_ACTION,
                        token=action_token,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Завтра",
                    callback_data=ConfirmActionCallback(
                        action=NUTRITION_GOAL_TOMORROW_ACTION,
                        token=action_token,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=NUTRITION_GOAL_CANCEL,
                )
            ],
        ]
    )


def build_nutrition_goal_disable_keyboard(
    goal_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚫 Да, отключить",
                    callback_data=NutritionGoalActionCallback(
                        action="disable_confirm",
                        goal_id=goal_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=SETTINGS_NUTRITION_GOALS,
                )
            ],
        ]
    )


def build_about_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Помощь", callback_data=SETTINGS_HELP)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)],
        ]
    )


def build_privacy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Мои данные", callback_data=SETTINGS_MY_DATA
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить все мои данные",
                    callback_data=SETTINGS_DELETE,
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)],
        ]
    )


def build_my_data_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_PRIVACY)]
        ]
    )


def build_delete_warning_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=SETTINGS_PRIVACY)],
            [
                InlineKeyboardButton(
                    text="🗑 Продолжить",
                    callback_data=SETTINGS_DELETE_CONTINUE,
                )
            ],
        ]
    )


def build_delete_phrase_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=SETTINGS_PRIVACY)]
        ]
    )


def build_settings_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_ABOUT)]
        ]
    )
