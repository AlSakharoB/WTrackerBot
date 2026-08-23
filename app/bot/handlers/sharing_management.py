from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.handlers.sharing import SHARE_BEARER_WARNING, sharing_service
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.sharing_management import (
    SHARE_REVOKE_ACTION,
    SHARE_ROTATE_ACTION,
    ShareManagementCallback,
    build_rotated_share_keyboard,
    build_share_management_confirmation_keyboard,
    build_share_management_detail_keyboard,
    build_share_management_keyboard,
)
from app.bot.states.sharing import ShareManagementStates
from app.db.models.share import SharePackageType
from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.services.action_lock import generate_action_token
from app.services.sharing import (
    OwnedSharePackage,
    OwnedSharePackagePage,
    ShareRuntimeStatus,
)
from app.sharing.payloads import SharePayloadLimits

router = Router(name=__name__)

STATUS_LABELS = {
    ShareRuntimeStatus.ACTIVE: "активна",
    ShareRuntimeStatus.REVOKED: "отозвана",
    ShareRuntimeStatus.EXPIRED: "истекла",
}


def management_list_text(
    package_page: OwnedSharePackagePage,
    package_type: SharePackageType,
    timezone_name: str,
) -> str:
    type_label = (
        "ингредиентов" if package_type is SharePackageType.INGREDIENTS else "блюд"
    )
    lines = [f"📦 <b>Мои ссылки: {type_label}</b>"]
    if not package_page.items:
        lines.append("\nВы ещё не создавали такие ссылки.")
        return "\n".join(lines)
    for index, item in enumerate(package_page.items, start=1):
        package = item.package
        lines.extend(
            [
                "",
                f"<b>{index}. {escape(item.title)}</b>",
                f"Объектов: {package.item_count}",
                f"Создана: {_format_date(package.created_at, timezone_name)}",
                f"Действует до: {_format_date(package.expires_at, timezone_name)}",
                f"Статус: {STATUS_LABELS[item.runtime_status]}",
                f"Завершённых импортов: {item.completed_imports}",
            ]
        )
    return "\n".join(lines)


def management_detail_text(
    item: OwnedSharePackage,
    timezone_name: str,
) -> str:
    package = item.package
    type_label = (
        "Ингредиенты"
        if package.package_type == SharePackageType.INGREDIENTS
        else "Блюда"
    )
    return f"""📦 <b>{escape(item.title)}</b>

Тип: {type_label}
Объектов: {package.item_count}
Создана: {_format_date(package.created_at, timezone_name)}
Действует до: {_format_date(package.expires_at, timezone_name)}
Статус: {STATUS_LABELS[item.runtime_status]}
Завершённых импортов: {item.completed_imports}"""


@router.callback_query(ShareManagementCallback.filter(F.action == "list"))
async def share_management_list_callback(
    callback: CallbackQuery,
    callback_data: ShareManagementCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await state.clear()
    try:
        package_type = SharePackageType(callback_data.package_type)
    except ValueError:
        await callback.answer("Раздел ссылок не найден.", show_alert=True)
        return
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    package_page = await service.list_owned_packages(
        current_user.id,
        package_type,
        page=callback_data.page,
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            management_list_text(package_page, package_type, current_user.timezone),
            reply_markup=build_share_management_keyboard(package_page, package_type),
        )


@router.callback_query(ShareManagementCallback.filter(F.action == "view"))
async def share_management_detail_callback(
    callback: CallbackQuery,
    callback_data: ShareManagementCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await state.clear()
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        item = await service.get_owned_package(
            callback_data.package_id,
            current_user.id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    package_type = SharePackageType(item.package.package_type)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            management_detail_text(item, current_user.timezone),
            reply_markup=build_share_management_detail_keyboard(
                item.package.id,
                package_type,
                callback_data.page,
                item.runtime_status,
            ),
        )


@router.callback_query(
    ShareManagementCallback.filter((F.action == "revoke") | (F.action == "rotate"))
)
async def share_management_confirmation_callback(
    callback: CallbackQuery,
    callback_data: ShareManagementCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        item = await service.get_owned_package(
            callback_data.package_id,
            current_user.id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    action = (
        SHARE_REVOKE_ACTION if callback_data.action == "revoke" else SHARE_ROTATE_ACTION
    )
    if (
        action == SHARE_REVOKE_ACTION
        and item.runtime_status is not ShareRuntimeStatus.ACTIVE
    ):
        await callback.answer("Ссылка уже не активна.", show_alert=True)
        return
    action_token = generate_action_token()
    package_type = SharePackageType(item.package.package_type)
    await state.set_state(ShareManagementStates.confirmation)
    await state.set_data(
        {
            "action_token": action_token,
            "management_action": action,
            "package_id": item.package.id,
            "package_type": package_type.value,
            "page": callback_data.page,
        }
    )
    text = (
        "Отозвать ссылку? Новые просмотры и импорты станут недоступны. "
        "Уже импортированные данные сохранятся."
        if action == SHARE_REVOKE_ACTION
        else "Создать новую ссылку? Старая ссылка сразу перестанет работать, "
        "а срок действия начнётся заново."
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_share_management_confirmation_keyboard(
                action=action,
                action_token=action_token,
                package_id=item.package.id,
                package_type=package_type,
                page=callback_data.page,
            ),
        )


@router.callback_query(
    ShareManagementStates.confirmation,
    ConfirmActionCallback.filter(F.action == SHARE_REVOKE_ACTION),
)
async def share_management_revoke_confirm_callback(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    data = await _management_confirmation_data(
        callback, state, callback_data, SHARE_REVOKE_ACTION
    )
    if data is None:
        return
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        await service.revoke_package(data["package_id"], current_user.id)
        item = await service.get_owned_package(data["package_id"], current_user.id)
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    await callback.answer("Ссылка отозвана")
    if callback.message is not None:
        await callback.message.edit_text(
            management_detail_text(item, current_user.timezone),
            reply_markup=build_share_management_detail_keyboard(
                item.package.id,
                SharePackageType(item.package.package_type),
                data["page"],
                item.runtime_status,
            ),
        )


@router.callback_query(
    ShareManagementStates.confirmation,
    ConfirmActionCallback.filter(F.action == SHARE_ROTATE_ACTION),
)
async def share_management_rotate_confirm_callback(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    data = await _management_confirmation_data(
        callback, state, callback_data, SHARE_ROTATE_ACTION
    )
    if data is None:
        return
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        created = await service.rotate_package(data["package_id"], current_user.id)
    except (NotFoundError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    await callback.answer("Новая ссылка создана")
    package_type = SharePackageType(created.package.package_type)
    expires_at = _format_date(created.package.expires_at, current_user.timezone)
    if callback.message is not None:
        await callback.message.edit_text(
            "🔄 <b>Новая ссылка готова</b>\n\n"
            f"Действует до {expires_at}. Старая ссылка больше не работает.\n\n"
            f"⚠️ {SHARE_BEARER_WARNING}",
            reply_markup=build_rotated_share_keyboard(
                package_id=created.package.id,
                package_type=package_type,
                page=data["page"],
                deep_link=created.deep_link,
                telegram_share_url=created.telegram_share_url,
            ),
        )


async def _management_confirmation_data(
    callback: CallbackQuery,
    state: FSMContext,
    callback_data: ConfirmActionCallback,
    expected_action: str,
) -> dict[str, int | str] | None:
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return None
    if (
        data.get("management_action") != expected_action
        or not isinstance(data.get("package_id"), int)
        or not isinstance(data.get("page"), int)
    ):
        await callback.answer(
            "Кнопка устарела. Откройте раздел заново.", show_alert=True
        )
        return None
    return data


def _format_date(value: datetime, timezone_name: str) -> str:
    return value.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y")
