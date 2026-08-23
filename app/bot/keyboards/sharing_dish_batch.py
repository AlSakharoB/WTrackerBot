from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.dishes import DISHES_NOOP, shortened_button_text
from app.search import SearchResult
from app.services.dishes import DishPage
from app.services.sharing import (
    BatchIngredientAction,
    DishConflictType,
    DishImportAction,
)

DISH_BATCH_IMPORT_ACTION = "share_dishes"
DISH_SELECTION_SEARCH = "shdsel:search"
DISH_SELECTION_RESET = "shdsel:reset"
DISH_SELECTION_CREATE = "shdsel:create"
DISH_SELECTION_CANCEL = "shdsel:cancel"
DISH_BATCH_CANCEL = "share:dishes:cancel"


class DishSelectionItemCallback(CallbackData, prefix="shdsi"):
    dish_id: int
    page: int


class DishSelectionPageCallback(CallbackData, prefix="shdsp"):
    page: int


class DishBatchPackageCallback(CallbackData, prefix="shbdp"):
    action: str
    package_id: int


class DishBatchImportCallback(CallbackData, prefix="shbdi"):
    action: str
    index: int


def build_dish_selection_keyboard(
    page: DishPage,
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for dish in page.items:
        marker = "☑️" if dish.id in selected_ids else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {shortened_button_text('🍲', dish.name)[2:]}",
                callback_data=DishSelectionItemCallback(
                    dish_id=dish.id,
                    page=page.page,
                ).pack(),
            )
        )
    _add_selection_create(builder, len(selected_ids))
    if page.pages > 1:
        previous = (
            DishSelectionPageCallback(page=page.page - 1).pack()
            if page.page > 1
            else DISHES_NOOP
        )
        following = (
            DishSelectionPageCallback(page=page.page + 1).pack()
            if page.page < page.pages
            else DISHES_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}", callback_data=DISHES_NOOP
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    _add_selection_footer(builder)
    return builder.as_markup()


def build_dish_selection_search_keyboard(
    results: list[SearchResult],
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for result in results:
        marker = "☑️" if result.entity_id in selected_ids else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {shortened_button_text('🍲', result.name)[2:]}",
                callback_data=DishSelectionItemCallback(
                    dish_id=result.entity_id,
                    page=0,
                ).pack(),
            )
        )
    _add_selection_create(builder, len(selected_ids))
    builder.row(
        InlineKeyboardButton(
            text="📋 Весь список",
            callback_data=DishSelectionPageCallback(page=1).pack(),
        ),
        InlineKeyboardButton(
            text="🔎 Искать снова", callback_data=DISH_SELECTION_SEARCH
        ),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_SELECTION_CANCEL)
    )
    return builder.as_markup()


def build_created_dish_batch_keyboard(
    *,
    package_id: int,
    deep_link: str,
    telegram_share_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Отправить в Telegram", url=telegram_share_url
                )
            ],
            [InlineKeyboardButton(text="🔗 Открыть ссылку", url=deep_link)],
            [
                InlineKeyboardButton(
                    text="🗑 Отозвать ссылку",
                    callback_data=DishBatchPackageCallback(
                        action="revoke", package_id=package_id
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="⬅️ К блюдам", callback_data="dishes:menu")],
        ]
    )


def build_dish_batch_preview_keyboard(
    action_token: str,
    *,
    has_ingredient_conflicts: bool,
    can_import: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_ingredient_conflicts:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Разобрать ингредиенты",
                    callback_data=DishBatchImportCallback(
                        action="ingredients", index=0
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="⚙️ Настроить блюда",
                callback_data=DishBatchImportCallback(action="dishes", index=0).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Импортировать набор",
                callback_data=(
                    ConfirmActionCallback(
                        action=DISH_BATCH_IMPORT_ACTION,
                        token=action_token,
                    ).pack()
                    if can_import
                    else DISHES_NOOP
                ),
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_BATCH_CANCEL)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_batch_ingredient_conflict_keyboard(
    *,
    index: int,
    total: int,
    selected: BatchIngredientAction | None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✓ " if selected is BatchIngredientAction.REUSE else "")
                + "Использовать мой",
                callback_data=DishBatchImportCallback(
                    action="reuse", index=index
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=(
                    "✓ "
                    if selected is BatchIngredientAction.COPY_WITH_GENERATED_NAME
                    else ""
                )
                + "Создать отдельную копию",
                callback_data=DishBatchImportCallback(
                    action="copy", index=index
                ).pack(),
            )
        ],
        _navigation_row("ingredient_view", index, total),
        [
            InlineKeyboardButton(
                text="✅ К проверке",
                callback_data=DishBatchImportCallback(
                    action="preview", index=index
                ).pack(),
            )
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_BATCH_CANCEL)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_batch_dish_plan_keyboard(
    *,
    index: int,
    total: int,
    conflict_type: DishConflictType,
    selected: DishImportAction,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if conflict_type is DishConflictType.NEW:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✓ " if selected is DishImportAction.CREATE else "")
                    + "Импортировать",
                    callback_data=DishBatchImportCallback(
                        action="dish_create", index=index
                    ).pack(),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✓ " if selected is DishImportAction.CREATE_COPY else "")
                    + "Создать отдельную копию",
                    callback_data=DishBatchImportCallback(
                        action="dish_copy", index=index
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=("✓ " if selected is DishImportAction.SKIP else "")
                + "Пропустить блюдо",
                callback_data=DishBatchImportCallback(
                    action="dish_skip", index=index
                ).pack(),
            )
        ]
    )
    rows.extend(
        [
            _navigation_row("dish_view", index, total),
            [
                InlineKeyboardButton(
                    text="✅ К проверке",
                    callback_data=DishBatchImportCallback(
                        action="preview", index=index
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_BATCH_CANCEL)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _navigation_row(action: str, index: int, total: int) -> list[InlineKeyboardButton]:
    row: list[InlineKeyboardButton] = []
    if index > 0:
        row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=DishBatchImportCallback(
                    action=action, index=index - 1
                ).pack(),
            )
        )
    row.append(
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data=DISHES_NOOP)
    )
    if index + 1 < total:
        row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=DishBatchImportCallback(
                    action=action, index=index + 1
                ).pack(),
            )
        )
    return row


def _add_selection_create(builder: InlineKeyboardBuilder, count: int) -> None:
    builder.row(
        InlineKeyboardButton(
            text=f"🔗 Создать ссылку ({count})",
            callback_data=DISH_SELECTION_CREATE,
        )
    )


def _add_selection_footer(builder: InlineKeyboardBuilder) -> None:
    builder.row(
        InlineKeyboardButton(text="🔎 Поиск", callback_data=DISH_SELECTION_SEARCH),
        InlineKeyboardButton(text="↺ Сбросить", callback_data=DISH_SELECTION_RESET),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_SELECTION_CANCEL)
    )
