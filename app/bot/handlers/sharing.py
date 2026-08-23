from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.ingredients import IngredientCallback
from app.bot.keyboards.sharing import (
    SHARE_CREATE_COPY_ACTION,
    SHARE_IMPORT_ACTION,
    SHARE_IMPORT_CANCEL,
    SHARE_KEEP_MINE_ACTION,
    SharePackageCallback,
    build_created_share_keyboard,
    build_import_cancelled_keyboard,
    build_import_conflict_keyboard,
    build_import_done_keyboard,
    build_import_preview_keyboard,
    build_revoked_share_keyboard,
)
from app.bot.states.sharing import ShareImportStates
from app.db.models.ingredient import Ingredient
from app.db.models.share import ShareImportStatus
from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import ShareRepository
from app.services.action_lock import generate_action_token
from app.services.sharing import (
    CreatedSharePackage,
    ExpiredShareLinkError,
    IngredientConflictType,
    IngredientImportResolution,
    IngredientImportResult,
    IngredientPackageAccess,
    IngredientPreflight,
    InvalidShareLinkError,
    SharingService,
)
from app.sharing.payloads import SharedIngredient, SharePayloadLimits
from app.utils.decimal import format_decimal

router = Router(name=__name__)


def sharing_service(
    session: AsyncSession,
    *,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> SharingService:
    return SharingService(
        ShareRepository(session),
        bot_username=bot_username,
        link_ttl_days=share_link_ttl_days,
        limits=share_payload_limits,
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )


def shared_ingredient_card(ingredient: SharedIngredient) -> str:
    return f"""🥕 <b>{escape(ingredient.name)}</b>

На 100 г:
🔥 {format_decimal(ingredient.kcal_per_100g)} ккал
🥩 Б: {format_decimal(ingredient.protein_per_100g)} г
🥑 Ж: {format_decimal(ingredient.fat_per_100g)} г
🍞 У: {format_decimal(ingredient.carbs_per_100g)} г"""


def created_share_card(
    created: CreatedSharePackage,
    ingredient: SharedIngredient,
) -> str:
    expires = created.package.expires_at.strftime("%d.%m.%Y")
    return f"""📦 <b>Ингредиент готов к отправке</b>

{shared_ingredient_card(ingredient)}

Ссылка действует до {expires}.
Получатель сам подтвердит импорт."""


def import_preview_card(ingredient: SharedIngredient) -> str:
    return f"""📦 <b>Вам отправили ингредиент</b>

{shared_ingredient_card(ingredient)}

Добавить в ваши ингредиенты?"""


def conflict_card(preflight: IngredientPreflight) -> str:
    existing = preflight.existing
    if existing is None:  # pragma: no cover - conflict invariant
        raise RuntimeError("Conflict has no existing ingredient")
    incoming = preflight.incoming
    return f"""⚠️ <b>Найден похожий ингредиент</b>

Ваш:
🥕 <b>{escape(existing.name)}</b>
{compact_nutrition(existing)}

Полученный:
🥕 <b>{escape(incoming.name)}</b>
{compact_nutrition(incoming)}"""


def compact_nutrition(ingredient: Ingredient | SharedIngredient) -> str:
    return (
        f"{format_decimal(ingredient.kcal_per_100g)} ккал · "
        f"Б {format_decimal(ingredient.protein_per_100g)} · "
        f"Ж {format_decimal(ingredient.fat_per_100g)} · "
        f"У {format_decimal(ingredient.carbs_per_100g)}"
    )


def previous_import_text(access: IngredientPackageAccess) -> str:
    imported = access.previous_import
    if imported is None:  # pragma: no cover - caller invariant
        raise RuntimeError("Previous import is missing")
    if imported.status == ShareImportStatus.PROCESSING:
        return "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
    return f"""Этот пакет уже был импортирован.

Создано ингредиентов: {imported.created_ingredients_count}
Использовано существующих: {imported.reused_ingredients_count}
Пропущено: {imported.skipped_ingredients_count}"""


async def handle_ingredient_share_start(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    token: str,
    *,
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
        access = await service.resolve_ingredient_token(token, current_user.id)
    except InvalidShareLinkError:
        try:
            dish_access = await service.resolve_dish_token(token, current_user.id)
        except (InvalidShareLinkError, ExpiredShareLinkError) as error:
            await message.answer(
                escape(str(error)),
                reply_markup=build_import_cancelled_keyboard(),
            )
            return
        from app.bot.handlers.sharing_dish import handle_dish_share_start

        await handle_dish_share_start(
            message,
            state,
            current_user,
            dish_access,
            service,
        )
        return
    except ExpiredShareLinkError as error:
        await message.answer(
            escape(str(error)),
            reply_markup=build_import_cancelled_keyboard(),
        )
        return
    if access.is_owner:
        await message.answer(
            "Это ваша ссылка. Вы можете отправить её другому пользователю "
            "или отозвать.",
            reply_markup=build_import_cancelled_keyboard(),
        )
        return
    if access.previous_import is not None:
        await message.answer(
            previous_import_text(access),
            reply_markup=build_import_done_keyboard(),
        )
        return
    if len(access.payload.ingredients) > 1:
        from app.bot.handlers.sharing_batch import handle_batch_ingredient_access

        await handle_batch_ingredient_access(
            message,
            state,
            current_user,
            access,
            service,
        )
        return

    action_token = generate_action_token()
    await state.update_data(
        package_id=access.package.id,
        action_token=action_token,
    )
    await state.set_state(ShareImportStates.preview)
    await message.answer(
        import_preview_card(access.payload.ingredients[0]),
        reply_markup=build_import_preview_keyboard(action_token),
    )


@router.callback_query(IngredientCallback.filter(F.action == "share"))
async def ingredient_share_callback(
    callback: CallbackQuery,
    callback_data: IngredientCallback,
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
        created = await service.create_ingredient_package(
            current_user.id,
            callback_data.ingredient_id,
        )
    except (NotFoundError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    ingredient = created.package.payload["ingredients"][0]
    shared = SharedIngredient.model_validate(ingredient)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            created_share_card(created, shared),
            reply_markup=build_created_share_keyboard(
                package_id=created.package.id,
                ingredient_id=callback_data.ingredient_id,
                page=callback_data.page,
                deep_link=created.deep_link,
                telegram_share_url=created.telegram_share_url,
            ),
        )


@router.callback_query(SharePackageCallback.filter(F.action == "revoke"))
async def share_revoke_callback(
    callback: CallbackQuery,
    callback_data: SharePackageCallback,
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
        await service.revoke_package(callback_data.package_id, current_user.id)
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Ссылка отозвана")
    if callback.message is not None:
        await callback.message.edit_text(
            "Ссылка отозвана и больше не может использоваться для импорта.",
            reply_markup=build_revoked_share_keyboard(
                callback_data.ingredient_id,
                callback_data.page,
            ),
        )


@router.callback_query(
    ShareImportStates.preview,
    ConfirmActionCallback.filter(F.action == SHARE_IMPORT_ACTION),
)
async def share_import_confirm_callback(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return
    package_id = data.get("package_id")
    if not isinstance(package_id, int):
        await callback.answer(
            "Кнопка устарела. Откройте ссылку заново.", show_alert=True
        )
        return
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        result = await service.import_ingredient(
            package_id,
            current_user.id,
            IngredientImportResolution.ADD,
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        await _show_import_error(callback, state, error)
        return
    if result.requires_resolution:
        action_token = generate_action_token()
        await state.update_data(action_token=action_token)
        await state.set_state(ShareImportStates.conflict)
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(
                conflict_card(result.preflight),
                reply_markup=build_import_conflict_keyboard(action_token),
            )
        return
    await _show_import_result(callback, state, result, IngredientImportResolution.ADD)


@router.callback_query(
    ShareImportStates.conflict,
    ConfirmActionCallback.filter(
        (F.action == SHARE_KEEP_MINE_ACTION) | (F.action == SHARE_CREATE_COPY_ACTION)
    ),
)
async def share_import_conflict_callback(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return
    package_id = data.get("package_id")
    if not isinstance(package_id, int):
        await callback.answer(
            "Кнопка устарела. Откройте ссылку заново.", show_alert=True
        )
        return
    resolution = (
        IngredientImportResolution.KEEP_MINE
        if callback_data.action == SHARE_KEEP_MINE_ACTION
        else IngredientImportResolution.CREATE_COPY
    )
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        result = await service.import_ingredient(
            package_id,
            current_user.id,
            resolution,
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        await _show_import_error(callback, state, error)
        return
    await _show_import_result(callback, state, result, resolution)


@router.callback_query(F.data == SHARE_IMPORT_CANCEL)
async def share_import_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Импорт отменён")
    if callback.message is not None:
        await callback.message.edit_text(
            "Импорт отменён. Данные не изменены.",
            reply_markup=build_import_cancelled_keyboard(),
        )


async def _show_import_error(
    callback: CallbackQuery,
    state: FSMContext,
    error: ValidationError,
) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            escape(str(error)),
            reply_markup=build_import_cancelled_keyboard(),
        )


async def _show_import_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: IngredientImportResult,
    resolution: IngredientImportResolution,
) -> None:
    await state.clear()
    await callback.answer()
    if result.already_completed:
        text = "Этот пакет уже был импортирован. Новая запись не создана."
    elif result.preflight.conflict_type is IngredientConflictType.EXACT_SAME:
        existing = result.preflight.existing
        if existing is None:  # pragma: no cover - preflight invariant
            raise RuntimeError("Exact match has no existing ingredient")
        existing_name = escape(existing.name)
        text = (
            f"Такой ингредиент уже есть у вас: «{existing_name}».\n\n"
            "Новая запись не создана."
        )
    elif resolution is IngredientImportResolution.KEEP_MINE:
        text = "Ваш ингредиент оставлен без изменений. Новая запись не создана."
    elif result.ingredient is not None:
        text = f"Ингредиент добавлен.\n\n{_ingredient_model_card(result.ingredient)}"
    else:
        text = "Импорт завершён без создания новой записи."
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_import_done_keyboard(
                result.ingredient.id if result.ingredient is not None else None
            ),
        )


def _ingredient_model_card(ingredient: Ingredient) -> str:
    return f"""🥕 <b>{escape(ingredient.name)}</b>

На 100 г:
🔥 {format_decimal(ingredient.kcal_per_100g)} ккал
🥩 Б: {format_decimal(ingredient.protein_per_100g)} г
🥑 Ж: {format_decimal(ingredient.fat_per_100g)} г
🍞 У: {format_decimal(ingredient.carbs_per_100g)} г"""
