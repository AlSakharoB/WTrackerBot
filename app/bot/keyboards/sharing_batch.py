from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.ingredients import INGREDIENTS_NOOP, ingredient_button_text
from app.search import SearchResult
from app.services.ingredients import IngredientPage
from app.services.sharing import BatchIngredientAction

SHARE_BATCH_IMPORT_ACTION = "share_batch"
SHARE_SELECTION_SEARCH = "shsel:search"
SHARE_SELECTION_RESET = "shsel:reset"
SHARE_SELECTION_CREATE = "shsel:create"
SHARE_SELECTION_CANCEL = "shsel:cancel"


class ShareSelectionItemCallback(CallbackData, prefix="shsi"):
    ingredient_id: int
    page: int


class ShareSelectionPageCallback(CallbackData, prefix="shsp"):
    page: int


class BatchSharePackageCallback(CallbackData, prefix="shbp"):
    action: str
    package_id: int


class BatchConflictCallback(CallbackData, prefix="shbc"):
    action: str
    index: int


def build_selection_keyboard(
    page: IngredientPage,
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ingredient in page.items:
        marker = "☑️" if ingredient.id in selected_ids else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {ingredient_button_text(ingredient.name)[2:]}",
                callback_data=ShareSelectionItemCallback(
                    ingredient_id=ingredient.id,
                    page=page.page,
                ).pack(),
            )
        )
    _add_selection_controls(builder, len(selected_ids))
    if page.pages > 1:
        previous = (
            ShareSelectionPageCallback(page=page.page - 1).pack()
            if page.page > 1
            else INGREDIENTS_NOOP
        )
        following = (
            ShareSelectionPageCallback(page=page.page + 1).pack()
            if page.page < page.pages
            else INGREDIENTS_NOOP
        )
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=previous),
            InlineKeyboardButton(
                text=f"{page.page}/{page.pages}", callback_data=INGREDIENTS_NOOP
            ),
            InlineKeyboardButton(text="▶️", callback_data=following),
        )
    _add_selection_footer(builder)
    return builder.as_markup()


def build_selection_search_keyboard(
    results: list[SearchResult],
    selected_ids: set[int],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for result in results:
        marker = "☑️" if result.entity_id in selected_ids else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {ingredient_button_text(result.name)[2:]}",
                callback_data=ShareSelectionItemCallback(
                    ingredient_id=result.entity_id,
                    page=0,
                ).pack(),
            )
        )
    _add_selection_controls(builder, len(selected_ids))
    builder.row(
        InlineKeyboardButton(
            text="📋 Весь список",
            callback_data=ShareSelectionPageCallback(page=1).pack(),
        ),
        InlineKeyboardButton(
            text="🔎 Искать снова", callback_data=SHARE_SELECTION_SEARCH
        ),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=SHARE_SELECTION_CANCEL)
    )
    return builder.as_markup()


def build_created_batch_share_keyboard(
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
                    callback_data=BatchSharePackageCallback(
                        action="revoke", package_id=package_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К ингредиентам", callback_data="ingredients:menu"
                )
            ],
        ]
    )


def build_batch_preview_keyboard(
    action_token: str,
    *,
    has_conflicts: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_conflicts:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Разобрать конфликты",
                    callback_data=BatchConflictCallback(action="open", index=0).pack(),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="✅ Импортировать",
                    callback_data=ConfirmActionCallback(
                        action=SHARE_BATCH_IMPORT_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="share:cancel")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_batch_conflict_keyboard(
    *,
    index: int,
    total: int,
    selected: BatchIngredientAction,
) -> InlineKeyboardMarkup:
    def label(action: BatchIngredientAction, text: str) -> str:
        return f"✓ {text}" if action is selected else text

    rows = [
        [
            InlineKeyboardButton(
                text=label(BatchIngredientAction.SKIP, "Пропустить"),
                callback_data=BatchConflictCallback(action="skip", index=index).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=label(BatchIngredientAction.REUSE, "Оставить мой"),
                callback_data=BatchConflictCallback(action="reuse", index=index).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=label(
                    BatchIngredientAction.COPY_WITH_GENERATED_NAME,
                    "Создать отдельную копию",
                ),
                callback_data=BatchConflictCallback(action="copy", index=index).pack(),
            )
        ],
    ]
    navigation: list[InlineKeyboardButton] = []
    if index > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=BatchConflictCallback(
                    action="view", index=index - 1
                ).pack(),
            )
        )
    navigation.append(
        InlineKeyboardButton(
            text=f"{index + 1}/{total}", callback_data=INGREDIENTS_NOOP
        )
    )
    if index + 1 < total:
        navigation.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=BatchConflictCallback(
                    action="view", index=index + 1
                ).pack(),
            )
        )
    rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Готово",
                callback_data=BatchConflictCallback(action="done", index=index).pack(),
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="share:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _add_selection_controls(
    builder: InlineKeyboardBuilder, selected_count: int
) -> None:
    builder.row(
        InlineKeyboardButton(
            text=f"🔗 Создать ссылку ({selected_count})",
            callback_data=SHARE_SELECTION_CREATE,
        )
    )


def _add_selection_footer(builder: InlineKeyboardBuilder) -> None:
    builder.row(
        InlineKeyboardButton(text="🔎 Поиск", callback_data=SHARE_SELECTION_SEARCH),
        InlineKeyboardButton(text="↺ Сбросить", callback_data=SHARE_SELECTION_RESET),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Отмена", callback_data=SHARE_SELECTION_CANCEL)
    )
