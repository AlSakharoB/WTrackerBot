from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.dishes import DISHES_NOOP, DishCallback
from app.services.sharing import BatchIngredientAction, DishImportAction

DISH_IMPORT_ACTION = "share_dish"
DISH_IMPORT_CANCEL = "share:dish:cancel"


class DishSharePackageCallback(CallbackData, prefix="shdp"):
    action: str
    package_id: int
    dish_id: int
    page: int


class DishImportCallback(CallbackData, prefix="shdi"):
    action: str
    index: int


def build_created_dish_share_keyboard(
    *,
    package_id: int,
    dish_id: int,
    page: int,
    deep_link: str,
    telegram_share_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Отправить в Telegram",
                    url=telegram_share_url,
                )
            ],
            [InlineKeyboardButton(text="🔗 Открыть ссылку", url=deep_link)],
            [
                InlineKeyboardButton(
                    text="🗑 Отозвать ссылку",
                    callback_data=DishSharePackageCallback(
                        action="revoke",
                        package_id=package_id,
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К блюду",
                    callback_data=DishCallback(
                        action="view",
                        dish_id=dish_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_revoked_dish_share_keyboard(
    dish_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К блюду",
                    callback_data=DishCallback(
                        action="view", dish_id=dish_id, page=page
                    ).pack(),
                )
            ]
        ]
    )


def build_dish_import_preview_keyboard(
    action_token: str,
    *,
    ingredient_conflicts: bool,
    dish_conflict: bool,
    can_import: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ingredient_conflicts:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Разобрать ингредиенты",
                    callback_data=DishImportCallback(
                        action="ingredients", index=0
                    ).pack(),
                )
            ]
        )
    if dish_conflict:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Решить конфликт блюда",
                    callback_data=DishImportCallback(action="dish", index=0).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ Импортировать",
                callback_data=(
                    ConfirmActionCallback(
                        action=DISH_IMPORT_ACTION,
                        token=action_token,
                    ).pack()
                    if can_import
                    else DISHES_NOOP
                ),
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_IMPORT_CANCEL)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dish_ingredient_conflict_keyboard(
    *,
    index: int,
    total: int,
    selected: BatchIngredientAction | None,
) -> InlineKeyboardMarkup:
    def label(action: BatchIngredientAction, text: str) -> str:
        return f"✓ {text}" if selected is action else text

    rows = [
        [
            InlineKeyboardButton(
                text=label(BatchIngredientAction.REUSE, "Использовать мой"),
                callback_data=DishImportCallback(action="reuse", index=index).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=label(
                    BatchIngredientAction.COPY_WITH_GENERATED_NAME,
                    "Создать отдельную копию",
                ),
                callback_data=DishImportCallback(action="copy", index=index).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="⛔ Не импортировать блюдо",
                callback_data=DishImportCallback(action="abort", index=index).pack(),
            )
        ],
    ]
    navigation: list[InlineKeyboardButton] = []
    if index > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=DishImportCallback(
                    action="ingredient_view", index=index - 1
                ).pack(),
            )
        )
    navigation.append(
        InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data=DISHES_NOOP)
    )
    if index + 1 < total:
        navigation.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=DishImportCallback(
                    action="ingredient_view", index=index + 1
                ).pack(),
            )
        )
    rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text="✅ К проверке",
                callback_data=DishImportCallback(action="preview", index=index).pack(),
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_IMPORT_CANCEL)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_dish_name_conflict_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Пропустить импорт блюда",
                    callback_data=DishImportCallback(
                        action=DishImportAction.SKIP.value, index=0
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Создать отдельную копию",
                    callback_data=DishImportCallback(
                        action=DishImportAction.CREATE_COPY.value, index=0
                    ).pack(),
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=DISH_IMPORT_CANCEL)],
        ]
    )


def build_dish_import_done_keyboard(dish_id: int | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if dish_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🍲 Открыть блюдо",
                    callback_data=DishCallback(
                        action="view", dish_id=dish_id, page=1
                    ).pack(),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🍲 Мои блюда", callback_data="dishes:list")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
