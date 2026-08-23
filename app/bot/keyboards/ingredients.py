from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import INGREDIENT_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.diary import DiarySourceCallback
from app.db.models.diary import DiaryEntryType
from app.search import SearchResult
from app.services.ingredients import IngredientField, IngredientPage

INGREDIENTS_ADD = "ingredients:add"
INGREDIENTS_SEARCH = "ingredients:search"
INGREDIENTS_LIST = "ingredients:list"
INGREDIENTS_BACK_MAIN = "ingredients:back_main"
INGREDIENTS_NOOP = "ingredients:noop"
INGREDIENT_CREATE_RESTART = "ingredient_create:restart"
INGREDIENT_CANCEL = "ingredient:cancel"


class IngredientsPageCallback(CallbackData, prefix="ingredients"):
    action: str
    page: int


class IngredientCallback(CallbackData, prefix="ingredient"):
    action: str
    ingredient_id: int
    page: int


class IngredientEditCallback(CallbackData, prefix="ingredient_edit"):
    field: IngredientField
    ingredient_id: int
    page: int


def ingredient_button_text(name: str, max_length: int = 48) -> str:
    shortened = name if len(name) <= max_length else f"{name[: max_length - 1]}…"
    return f"🥕 {shortened}"


def build_ingredients_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data=INGREDIENTS_ADD)],
            [
                InlineKeyboardButton(text="🔎 Найти", callback_data=INGREDIENTS_SEARCH),
                InlineKeyboardButton(
                    text="📋 Все ингредиенты",
                    callback_data=INGREDIENTS_LIST,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=INGREDIENTS_BACK_MAIN,
                )
            ],
        ]
    )


def build_ingredient_list_keyboard(page: IngredientPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ingredient in page.items:
        builder.row(
            InlineKeyboardButton(
                text=ingredient_button_text(ingredient.name),
                callback_data=IngredientCallback(
                    action="view",
                    ingredient_id=ingredient.id,
                    page=page.page,
                ).pack(),
            )
        )

    if page.pages > 1:
        previous_data = (
            IngredientsPageCallback(action="page", page=page.page - 1).pack()
            if page.page > 1
            else INGREDIENTS_NOOP
        )
        next_data = (
            IngredientsPageCallback(action="page", page=page.page + 1).pack()
            if page.page < page.pages
            else INGREDIENTS_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous_data),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=INGREDIENTS_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=next_data),
        )

    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data=INGREDIENTS_ADD),
        InlineKeyboardButton(text="🔎 Найти", callback_data=INGREDIENTS_SEARCH),
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К ингредиентам",
            callback_data="ingredients:menu",
        )
    )
    return builder.as_markup()


def build_search_results_keyboard(
    results: list[SearchResult],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for result in results:
        builder.row(
            InlineKeyboardButton(
                text=ingredient_button_text(result.name),
                callback_data=IngredientCallback(
                    action="view",
                    ingredient_id=result.entity_id,
                    page=1,
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔎 Искать снова", callback_data=INGREDIENTS_SEARCH)
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ingredients:menu"))
    return builder.as_markup()


def build_search_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать ингредиент",
                    callback_data=INGREDIENTS_ADD,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Искать снова",
                    callback_data=INGREDIENTS_SEARCH,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="ingredients:menu",
                )
            ],
        ]
    )


def build_ingredient_detail_keyboard(
    ingredient_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ В рацион",
                    callback_data=DiarySourceCallback(
                        entry_type=DiaryEntryType.INGREDIENT,
                        source_id=ingredient_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📤 Поделиться",
                    callback_data=IngredientCallback(
                        action="share",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=IngredientCallback(
                        action="edit",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=IngredientCallback(
                        action="delete",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=IngredientsPageCallback(
                        action="page",
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_ingredient_edit_keyboard(
    ingredient_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    labels = {
        IngredientField.NAME: "Название",
        IngredientField.KCAL: "Калории",
        IngredientField.PROTEIN: "Белки",
        IngredientField.FAT: "Жиры",
        IngredientField.CARBS: "Углеводы",
    }
    builder = InlineKeyboardBuilder()
    for field, label in labels.items():
        builder.button(
            text=label,
            callback_data=IngredientEditCallback(
                field=field,
                ingredient_id=ingredient_id,
                page=page,
            ).pack(),
        )
    builder.adjust(2, 2, 1)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=IngredientCallback(
                action="view",
                ingredient_id=ingredient_id,
                page=page,
            ).pack(),
        )
    )
    return builder.as_markup()


def build_delete_confirmation_keyboard(
    ingredient_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=IngredientCallback(
                        action="delete_confirm",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=IngredientCallback(
                        action="view",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_create_confirmation_keyboard(action_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Сохранить",
                    callback_data=ConfirmActionCallback(
                        action=INGREDIENT_SAVE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=INGREDIENT_CREATE_RESTART,
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=INGREDIENT_CANCEL,
                ),
            ],
        ]
    )


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=INGREDIENT_CANCEL,
                )
            ]
        ]
    )
