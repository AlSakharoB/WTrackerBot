from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.settings import SETTINGS_MENU
from app.db.models.reminder import ReminderSetting, ReminderType
from app.services.reminders import WEEKDAY_LABELS

REMINDER_CANCEL = "reminder:cancel"
REMINDER_TODAY = "reminder:today"


class ReminderTypeCallback(CallbackData, prefix="remtype"):
    reminder_type: ReminderType


class ReminderWeekdayCallback(CallbackData, prefix="remday"):
    reminder_type: ReminderType
    weekday: int


class ReminderActionCallback(CallbackData, prefix="remact"):
    action: str
    reminder_type: ReminderType


def build_reminders_menu_keyboard(
    settings: list[ReminderSetting],
) -> InlineKeyboardMarkup:
    enabled = {setting.reminder_type for setting in settings if setting.enabled}
    rows: list[list[InlineKeyboardButton]] = []
    for reminder_type, label in (
        (ReminderType.WEIGH_IN, "⚖️ Взвешивание"),
        (ReminderType.NUTRITION, "🥗 КБЖУ"),
    ):
        action = "Изменить" if reminder_type in enabled else "Настроить"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{label} · {action}",
                    callback_data=ReminderTypeCallback(
                        reminder_type=reminder_type
                    ).pack(),
                )
            ]
        )
        if reminder_type in enabled:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🔕 Отключить {label.split(' ', 1)[1]}",
                        callback_data=ReminderActionCallback(
                            action="disable_menu",
                            reminder_type=reminder_type,
                        ).pack(),
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=SETTINGS_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_weekdays_keyboard(
    reminder_type: ReminderType,
    weekdays_mask: int,
) -> InlineKeyboardMarkup:
    day_buttons = [
        InlineKeyboardButton(
            text=f"{'✓ ' if weekdays_mask & (1 << day) else ''}{label}",
            callback_data=ReminderWeekdayCallback(
                reminder_type=reminder_type,
                weekday=day,
            ).pack(),
        )
        for day, label in enumerate(WEEKDAY_LABELS)
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            day_buttons[:4],
            day_buttons[4:],
            [
                InlineKeyboardButton(
                    text="➡️ Указать время",
                    callback_data=ReminderActionCallback(
                        action="choose_time",
                        reminder_type=reminder_type,
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=REMINDER_CANCEL)],
        ]
    )


def build_reminder_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=REMINDER_CANCEL)]
        ]
    )


def build_reminder_notification_keyboard(
    reminder_type: ReminderType,
) -> InlineKeyboardMarkup:
    action_button = (
        InlineKeyboardButton(text="➕ Добавить вес", callback_data="weight:add")
        if reminder_type is ReminderType.WEIGH_IN
        else InlineKeyboardButton(text="📅 Сегодня", callback_data=REMINDER_TODAY)
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [action_button],
            [
                InlineKeyboardButton(
                    text="🔕 Отключить",
                    callback_data=ReminderActionCallback(
                        action="disable_notice",
                        reminder_type=reminder_type,
                    ).pack(),
                )
            ],
        ]
    )
