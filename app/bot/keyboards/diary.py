from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import DIARY_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.settings import SETTINGS_NUTRITION_GOALS
from app.db.models.diary import DiaryEntryType, MealType
from app.services.diary import DiaryEntryPage
from app.services.dishes import DishPage
from app.services.ingredients import IngredientPage
from app.utils.decimal import format_decimal

DIARY_ADD = "diary:add"
DIARY_CHOOSE_DATE = "diary:choose_date"
DIARY_EDIT = "diary:edit"
DIARY_BACK_DAY = "diary:back_day"
DIARY_BACK_MAIN = "diary:back_main"
DIARY_CANCEL = "diary:cancel"
DIARY_NOOP = "diary:noop"


class DiarySourcePageCallback(CallbackData, prefix="dap"):
    entry_type: DiaryEntryType
    page: int


class DiarySourceCallback(CallbackData, prefix="das"):
    entry_type: DiaryEntryType
    source_id: int


class DiaryDishPortionCallback(CallbackData, prefix="dad"):
    dish_id: int
    mode: str


class DiaryMealCallback(CallbackData, prefix="dam"):
    meal_type: MealType


class DiaryDateCallback(CallbackData, prefix="dat"):
    action: str


class DiaryEntryCallback(CallbackData, prefix="dae"):
    action: str
    entry_id: int
    page: int


class DiaryEntryMealCallback(CallbackData, prefix="daem"):
    entry_id: int
    meal_type: MealType
    page: int


class DiaryEditPageCallback(CallbackData, prefix="dep"):
    page: int


def _shorten(name: str, length: int = 45) -> str:
    return name if len(name) <= length else f"{name[: length - 1]}…"


def build_add_food_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥕 Ингредиент",
                    callback_data=DiarySourcePageCallback(
                        entry_type=DiaryEntryType.INGREDIENT,
                        page=1,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🍲 Блюдо",
                    callback_data=DiarySourcePageCallback(
                        entry_type=DiaryEntryType.DISH,
                        page=1,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=DIARY_CANCEL,
                )
            ],
        ]
    )


def build_source_picker_keyboard(
    page: IngredientPage | DishPage,
    entry_type: DiaryEntryType,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    icon = "🥕" if entry_type is DiaryEntryType.INGREDIENT else "🍲"
    for item in page.items:
        builder.row(
            InlineKeyboardButton(
                text=f"{icon} {_shorten(item.name)}",
                callback_data=DiarySourceCallback(
                    entry_type=entry_type,
                    source_id=item.id,
                ).pack(),
            )
        )
    if page.pages > 1:
        previous = (
            DiarySourcePageCallback(
                entry_type=entry_type,
                page=page.page - 1,
            ).pack()
            if page.page > 1
            else DIARY_NOOP
        )
        following = (
            DiarySourcePageCallback(
                entry_type=entry_type,
                page=page.page + 1,
            ).pack()
            if page.page < page.pages
            else DIARY_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=DIARY_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data=DIARY_ADD),
        InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL),
    )
    return builder.as_markup()


def build_dish_portion_keyboard(
    dish_id: int,
    total_weight: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🍲 Всё блюдо — {total_weight} г",
                    callback_data=DiaryDishPortionCallback(
                        dish_id=dish_id,
                        mode="whole",
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚖️ Указать граммы",
                    callback_data=DiaryDishPortionCallback(
                        dish_id=dish_id,
                        mode="custom",
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL)],
        ]
    )


def build_meal_keyboard() -> InlineKeyboardMarkup:
    labels = {
        MealType.BREAKFAST: "🌅 Завтрак",
        MealType.LUNCH: "☀️ Обед",
        MealType.DINNER: "🌙 Ужин",
        MealType.SNACK: "🍎 Перекус",
        MealType.OTHER: "🍽 Другое",
    }
    builder = InlineKeyboardBuilder()
    for meal_type, label in labels.items():
        builder.button(
            text=label,
            callback_data=DiaryMealCallback(meal_type=meal_type).pack(),
        )
    builder.adjust(2, 2, 1)
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL))
    return builder.as_markup()


def build_date_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📅 Сегодня",
                    callback_data=DiaryDateCallback(action="today").pack(),
                ),
                InlineKeyboardButton(
                    text="📆 Другая дата",
                    callback_data=DiaryDateCallback(action="custom").pack(),
                ),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL)],
        ]
    )


def build_save_keyboard(action_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Добавить",
                    callback_data=ConfirmActionCallback(
                        action=DIARY_SAVE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL)],
        ]
    )


def build_day_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить еду", callback_data=DIARY_ADD)],
            [
                InlineKeyboardButton(
                    text="🎯 Цели КБЖУ",
                    callback_data=SETTINGS_NUTRITION_GOALS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="📆 Выбрать дату",
                    callback_data=DIARY_CHOOSE_DATE,
                ),
                InlineKeyboardButton(
                    text="✏️ Изменить рацион",
                    callback_data=DIARY_EDIT,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=DIARY_BACK_MAIN,
                )
            ],
        ]
    )


def build_entry_list_keyboard(page: DiaryEntryPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in page.items:
        builder.row(
            InlineKeyboardButton(
                text=(
                    f"{_shorten(entry.source_name, 28)} — "
                    f"{format_decimal(entry.grams)} г — "
                    f"{format_decimal(entry.kcal_snapshot)} ккал"
                ),
                callback_data=DiaryEntryCallback(
                    action="view",
                    entry_id=entry.id,
                    page=page.page,
                ).pack(),
            )
        )
    if page.pages > 1:
        previous = (
            DiaryEditPageCallback(page=page.page - 1).pack()
            if page.page > 1
            else DIARY_NOOP
        )
        following = (
            DiaryEditPageCallback(page=page.page + 1).pack()
            if page.page < page.pages
            else DIARY_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=DIARY_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    builder.row(InlineKeyboardButton(text="⬅️ К рациону", callback_data=DIARY_BACK_DAY))
    return builder.as_markup()


def build_entry_actions_keyboard(entry_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Граммы",
                    callback_data=DiaryEntryCallback(
                        action="grams",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🔄 Приём пищи",
                    callback_data=DiaryEntryCallback(
                        action="meal",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📆 Перенести",
                    callback_data=DiaryEntryCallback(
                        action="date",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=DiaryEntryCallback(
                        action="delete",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=DiaryEditPageCallback(page=page).pack(),
                )
            ],
        ]
    )


def build_entry_meal_keyboard(entry_id: int, page: int) -> InlineKeyboardMarkup:
    labels = {
        MealType.BREAKFAST: "🌅 Завтрак",
        MealType.LUNCH: "☀️ Обед",
        MealType.DINNER: "🌙 Ужин",
        MealType.SNACK: "🍎 Перекус",
        MealType.OTHER: "🍽 Другое",
    }
    builder = InlineKeyboardBuilder()
    for meal_type, label in labels.items():
        builder.button(
            text=label,
            callback_data=DiaryEntryMealCallback(
                entry_id=entry_id,
                meal_type=meal_type,
                page=page,
            ).pack(),
        )
    builder.adjust(2, 2, 1)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=DiaryEntryCallback(
                action="view",
                entry_id=entry_id,
                page=page,
            ).pack(),
        )
    )
    return builder.as_markup()


def build_entry_delete_keyboard(entry_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=DiaryEntryCallback(
                        action="delete_confirm",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=DiaryEntryCallback(
                        action="view",
                        entry_id=entry_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DIARY_CANCEL)]
        ]
    )
