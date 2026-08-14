from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.actions import GOAL_SAVE_ACTION, ConfirmActionCallback

GOAL_MENU = "goal:menu"
GOAL_CREATE = "goal:create"
GOAL_FLOW_CANCEL = "goal:flow_cancel"
GOAL_BACK_MAIN = "goal:back_main"


class GoalDateCallback(CallbackData, prefix="gdate"):
    mode: str


class GoalActionCallback(CallbackData, prefix="gact"):
    action: str
    goal_id: int


def build_empty_goal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать цель", callback_data=GOAL_CREATE)],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=GOAL_BACK_MAIN,
                )
            ],
        ]
    )


def build_active_goal_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Заменить цель",
                    callback_data=GoalActionCallback(
                        action="replace",
                        goal_id=goal_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Завершить",
                    callback_data=GoalActionCallback(
                        action="complete",
                        goal_id=goal_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отменить цель",
                    callback_data=GoalActionCallback(
                        action="cancel",
                        goal_id=goal_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=GOAL_BACK_MAIN,
                )
            ],
        ]
    )


def build_achieved_goal_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Завершить цель",
                    callback_data=GoalActionCallback(
                        action="complete",
                        goal_id=goal_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Поставить новую цель",
                    callback_data=GoalActionCallback(
                        action="replace",
                        goal_id=goal_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=GOAL_BACK_MAIN,
                )
            ],
        ]
    )


def build_goal_without_progress_keyboard(goal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вес", callback_data="weight:add")],
            [
                InlineKeyboardButton(
                    text="🔄 Заменить цель",
                    callback_data=GoalActionCallback(
                        action="replace",
                        goal_id=goal_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отменить цель",
                    callback_data=GoalActionCallback(
                        action="cancel",
                        goal_id=goal_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=GOAL_BACK_MAIN,
                )
            ],
        ]
    )


def build_goal_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без срока",
                    callback_data=GoalDateCallback(mode="none").pack(),
                ),
                InlineKeyboardButton(
                    text="📆 Указать срок",
                    callback_data=GoalDateCallback(mode="custom").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=GOAL_FLOW_CANCEL,
                )
            ],
        ]
    )


def build_goal_save_keyboard(
    replace_existing: bool,
    action_token: str,
) -> InlineKeyboardMarkup:
    label = "🔄 Заменить цель" if replace_existing else "✅ Создать цель"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ConfirmActionCallback(
                        action=GOAL_SAVE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=GOAL_FLOW_CANCEL,
                )
            ],
        ]
    )


def build_goal_action_confirmation_keyboard(
    goal_id: int,
    action: str,
) -> InlineKeyboardMarkup:
    label = "✅ Да, завершить" if action == "complete" else "❌ Да, отменить"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=GoalActionCallback(
                        action=f"{action}_confirm",
                        goal_id=goal_id,
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=GOAL_MENU)],
        ]
    )


def build_goal_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=GOAL_FLOW_CANCEL,
                )
            ]
        ]
    )
