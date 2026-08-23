from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import DISH_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.diary import DiarySourceCallback
from app.db.models.diary import DiaryEntryType
from app.search import SearchResult
from app.services.dishes import DishComponent, DishPage
from app.services.ingredients import IngredientPage

DISHES_CREATE = "dishes:create"
DISHES_SEARCH = "dishes:search"
DISHES_LIST = "dishes:list"
DISHES_MENU = "dishes:menu"
DISHES_BACK_MAIN = "dishes:back_main"
DISHES_NOOP = "dishes:noop"
DISH_EDITOR_ADD = "dish_editor:add"
DISH_EDITOR_RENAME = "dish_editor:rename"
DISH_EDITOR_CHANGE = "dish_editor:change"
DISH_EDITOR_REMOVE = "dish_editor:remove"
DISH_EDITOR_INGREDIENT_SEARCH = "dish_editor:ingredient_search"
DISH_EDITOR_CANCEL = "dish_editor:cancel"


class DishesPageCallback(CallbackData, prefix="dishes"):
    action: str
    page: int


class DishCallback(CallbackData, prefix="dish"):
    action: str
    dish_id: int
    page: int


class DishIngredientCallback(CallbackData, prefix="dish_ing"):
    action: str
    ingredient_id: int


class DishIngredientPageCallback(CallbackData, prefix="dish_ing_page"):
    page: int


def shortened_button_text(icon: str, name: str, max_length: int = 46) -> str:
    shortened = name if len(name) <= max_length else f"{name[: max_length - 1]}…"
    return f"{icon} {shortened}"


def build_dishes_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать блюдо", callback_data=DISHES_CREATE
                )
            ],
            [
                InlineKeyboardButton(text="🔎 Найти", callback_data=DISHES_SEARCH),
                InlineKeyboardButton(text="📋 Все блюда", callback_data=DISHES_LIST),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Главное меню",
                    callback_data=DISHES_BACK_MAIN,
                )
            ],
        ]
    )


def build_dish_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=DISH_EDITOR_CANCEL,
                )
            ]
        ]
    )


def build_dish_list_keyboard(page: DishPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for dish in page.items:
        builder.row(
            InlineKeyboardButton(
                text=shortened_button_text("🍲", dish.name),
                callback_data=DishCallback(
                    action="view",
                    dish_id=dish.id,
                    page=page.page,
                ).pack(),
            )
        )
    if page.pages > 1:
        previous = (
            DishesPageCallback(action="page", page=page.page - 1).pack()
            if page.page > 1
            else DISHES_NOOP
        )
        following = (
            DishesPageCallback(action="page", page=page.page + 1).pack()
            if page.page < page.pages
            else DISHES_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=DISHES_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    builder.row(
        InlineKeyboardButton(text="➕ Создать", callback_data=DISHES_CREATE),
        InlineKeyboardButton(text="🔎 Найти", callback_data=DISHES_SEARCH),
    )
    builder.row(InlineKeyboardButton(text="⬅️ К блюдам", callback_data=DISHES_MENU))
    return builder.as_markup()


def build_dish_detail_keyboard(dish_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ В рацион",
                    callback_data=DiarySourceCallback(
                        entry_type=DiaryEntryType.DISH,
                        source_id=dish_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧾 Состав",
                    callback_data=DishCallback(
                        action="composition",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="✏️ Редактировать",
                    callback_data=DishCallback(
                        action="edit",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить",
                    callback_data=DishCallback(
                        action="delete",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К списку",
                    callback_data=DishesPageCallback(action="page", page=page).pack(),
                )
            ],
        ]
    )


def build_dish_composition_keyboard(dish_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К блюду",
                    callback_data=DishCallback(
                        action="view",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ]
        ]
    )


def build_dish_delete_keyboard(dish_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить",
                    callback_data=DishCallback(
                        action="delete_confirm",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=DishCallback(
                        action="view",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_dish_editor_keyboard(
    has_components: bool,
    action_token: str,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="➕ Добавить ингредиент",
                callback_data=DISH_EDITOR_ADD,
            ),
            InlineKeyboardButton(
                text="✏️ Название",
                callback_data=DISH_EDITOR_RENAME,
            ),
        ]
    ]
    if has_components:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚖️ Изменить граммы",
                    callback_data=DISH_EDITOR_CHANGE,
                ),
                InlineKeyboardButton(
                    text="➖ Удалить из состава",
                    callback_data=DISH_EDITOR_REMOVE,
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Сохранить блюдо",
                    callback_data=ConfirmActionCallback(
                        action=DISH_SAVE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data=DISH_EDITOR_CANCEL,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_ingredient_picker_keyboard(page: IngredientPage) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ingredient in page.items:
        builder.row(
            InlineKeyboardButton(
                text=shortened_button_text("🥕", ingredient.name),
                callback_data=DishIngredientCallback(
                    action="select",
                    ingredient_id=ingredient.id,
                ).pack(),
            )
        )
    if page.pages > 1:
        previous = (
            DishIngredientPageCallback(page=page.page - 1).pack()
            if page.page > 1
            else DISHES_NOOP
        )
        following = (
            DishIngredientPageCallback(page=page.page + 1).pack()
            if page.page < page.pages
            else DISHES_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}",
                callback_data=DISHES_NOOP,
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    if page.total:
        builder.row(
            InlineKeyboardButton(
                text="🔎 Найти ингредиент",
                callback_data=DISH_EDITOR_INGREDIENT_SEARCH,
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ К рецепту", callback_data="dish_editor:back")
    )
    return builder.as_markup()


def build_ingredient_search_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Все ингредиенты",
                    callback_data=DISH_EDITOR_ADD,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К рецепту",
                    callback_data="dish_editor:back",
                )
            ],
        ]
    )


def build_ingredient_search_results_keyboard(
    results: list[SearchResult],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for result in results:
        builder.row(
            InlineKeyboardButton(
                text=shortened_button_text("🥕", result.name),
                callback_data=DishIngredientCallback(
                    action="select",
                    ingredient_id=result.entity_id,
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🔎 Искать снова",
            callback_data=DISH_EDITOR_INGREDIENT_SEARCH,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📋 Все ингредиенты",
            callback_data=DISH_EDITOR_ADD,
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="⬅️ К рецепту",
            callback_data="dish_editor:back",
        )
    )
    return builder.as_markup()


def build_component_picker_keyboard(
    components: list[DishComponent],
    action: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for component in components:
        builder.row(
            InlineKeyboardButton(
                text=shortened_button_text("🥕", component.ingredient.name),
                callback_data=DishIngredientCallback(
                    action=action,
                    ingredient_id=component.ingredient.id,
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ К рецепту", callback_data="dish_editor:back")
    )
    return builder.as_markup()


def build_dish_search_results_keyboard(
    results: list[SearchResult],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for result in results:
        builder.row(
            InlineKeyboardButton(
                text=shortened_button_text("🍲", result.name),
                callback_data=DishCallback(
                    action="view",
                    dish_id=result.entity_id,
                    page=1,
                ).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text="🔎 Искать снова", callback_data=DISHES_SEARCH)
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=DISHES_MENU))
    return builder.as_markup()


def build_dish_search_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Создать блюдо",
                    callback_data=DISHES_CREATE,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Искать снова",
                    callback_data=DISHES_SEARCH,
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=DISHES_MENU,
                )
            ],
        ]
    )
