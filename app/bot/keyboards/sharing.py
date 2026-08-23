from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.ingredients import IngredientCallback

SHARE_IMPORT_ACTION = "share_import"
SHARE_KEEP_MINE_ACTION = "share_keep"
SHARE_CREATE_COPY_ACTION = "share_copy"
SHARE_IMPORT_CANCEL = "share:cancel"


class SharePackageCallback(CallbackData, prefix="shpkg"):
    action: str
    package_id: int
    ingredient_id: int
    page: int


def build_created_share_keyboard(
    *,
    package_id: int,
    ingredient_id: int,
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
                    callback_data=SharePackageCallback(
                        action="revoke",
                        package_id=package_id,
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ К ингредиенту",
                    callback_data=IngredientCallback(
                        action="view",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ],
        ]
    )


def build_revoked_share_keyboard(
    ingredient_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ К ингредиенту",
                    callback_data=IngredientCallback(
                        action="view",
                        ingredient_id=ingredient_id,
                        page=page,
                    ).pack(),
                )
            ]
        ]
    )


def build_import_preview_keyboard(action_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Добавить",
                    callback_data=ConfirmActionCallback(
                        action=SHARE_IMPORT_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=SHARE_IMPORT_CANCEL,
                )
            ],
        ]
    )


def build_import_conflict_keyboard(action_token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Оставить мой",
                    callback_data=ConfirmActionCallback(
                        action=SHARE_KEEP_MINE_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Создать отдельную копию",
                    callback_data=ConfirmActionCallback(
                        action=SHARE_CREATE_COPY_ACTION,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=SHARE_IMPORT_CANCEL,
                )
            ],
        ]
    )


def build_import_done_keyboard(
    ingredient_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ingredient_id is not None:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🥕 Открыть ингредиент",
                    callback_data=IngredientCallback(
                        action="view",
                        ingredient_id=ingredient_id,
                        page=1,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🥕 Мои ингредиенты",
                callback_data="ingredients:list",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_import_cancelled_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🥕 К ингредиентам",
                    callback_data="ingredients:menu",
                )
            ]
        ]
    )
