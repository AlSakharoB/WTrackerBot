from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.actions import ConfirmActionCallback
from app.db.models.share import SharePackageType
from app.services.sharing import OwnedSharePackagePage, ShareRuntimeStatus

SHARE_REVOKE_ACTION = "share_revoke_manage"
SHARE_ROTATE_ACTION = "share_rotate_manage"


class ShareManagementCallback(CallbackData, prefix="shm"):
    action: str
    package_type: str
    package_id: int
    page: int


def management_callback(
    action: str,
    package_type: SharePackageType,
    *,
    package_id: int = 0,
    page: int = 1,
) -> str:
    return ShareManagementCallback(
        action=action,
        package_type=package_type.value,
        package_id=package_id,
        page=page,
    ).pack()


def build_share_management_keyboard(
    package_page: OwnedSharePackagePage,
    package_type: SharePackageType,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=("✓ " if package_type is SharePackageType.INGREDIENTS else "")
            + "Ингредиенты",
            callback_data=management_callback("list", SharePackageType.INGREDIENTS),
        ),
        InlineKeyboardButton(
            text=("✓ " if package_type is SharePackageType.DISHES else "") + "Блюда",
            callback_data=management_callback("list", SharePackageType.DISHES),
        ),
    )
    for index, item in enumerate(package_page.items, start=1):
        status_icon = {
            ShareRuntimeStatus.ACTIVE: "🟢",
            ShareRuntimeStatus.REVOKED: "🔴",
            ShareRuntimeStatus.EXPIRED: "⚪",
        }[item.runtime_status]
        title = item.title if len(item.title) <= 36 else f"{item.title[:35]}…"
        builder.row(
            InlineKeyboardButton(
                text=f"{status_icon} {index}. {title}",
                callback_data=management_callback(
                    "view",
                    package_type,
                    package_id=item.package.id,
                    page=package_page.page,
                ),
            )
        )
    if package_page.pages > 1:
        previous_page = max(package_page.page - 1, 1)
        next_page = min(package_page.page + 1, package_page.pages)
        builder.row(
            InlineKeyboardButton(
                text="◀️",
                callback_data=management_callback(
                    "list", package_type, page=previous_page
                ),
            ),
            InlineKeyboardButton(
                text=f"{package_page.page}/{package_page.pages}",
                callback_data=management_callback(
                    "list", package_type, page=package_page.page
                ),
            ),
            InlineKeyboardButton(
                text="▶️",
                callback_data=management_callback("list", package_type, page=next_page),
            ),
        )
    back_callback = (
        "ingredients:menu"
        if package_type is SharePackageType.INGREDIENTS
        else "dishes:menu"
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback))
    return builder.as_markup()


def build_share_management_detail_keyboard(
    package_id: int,
    package_type: SharePackageType,
    page: int,
    runtime_status: ShareRuntimeStatus,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if runtime_status is ShareRuntimeStatus.ACTIVE:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Отозвать ссылку",
                    callback_data=management_callback(
                        "revoke",
                        package_type,
                        package_id=package_id,
                        page=page,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Создать новую ссылку",
                callback_data=management_callback(
                    "rotate",
                    package_type,
                    package_id=package_id,
                    page=page,
                ),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ К списку",
                callback_data=management_callback("list", package_type, page=page),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_share_management_confirmation_keyboard(
    *,
    action: str,
    action_token: str,
    package_id: int,
    package_type: SharePackageType,
    page: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=ConfirmActionCallback(
                        action=action,
                        token=action_token,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Отмена",
                    callback_data=management_callback(
                        "view",
                        package_type,
                        package_id=package_id,
                        page=page,
                    ),
                )
            ],
        ]
    )


def build_rotated_share_keyboard(
    *,
    package_id: int,
    package_type: SharePackageType,
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
                    text="⬅️ К ссылке",
                    callback_data=management_callback(
                        "view",
                        package_type,
                        package_id=package_id,
                        page=page,
                    ),
                )
            ],
        ]
    )
