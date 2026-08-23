from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.handlers.sharing import compact_nutrition, sharing_service
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.dishes import DishCallback, build_dishes_menu_keyboard
from app.bot.keyboards.sharing_dish import (
    DISH_IMPORT_ACTION,
    DISH_IMPORT_CANCEL,
    DishImportCallback,
    DishSharePackageCallback,
    build_created_dish_share_keyboard,
    build_dish_import_done_keyboard,
    build_dish_import_preview_keyboard,
    build_dish_ingredient_conflict_keyboard,
    build_dish_name_conflict_keyboard,
    build_revoked_dish_share_keyboard,
)
from app.bot.states.sharing import ShareImportStates
from app.db.models.share import ShareImportStatus
from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.services.action_lock import generate_action_token
from app.services.sharing import (
    BatchIngredientAction,
    CreatedSharePackage,
    DishConflictType,
    DishImportAction,
    DishImportPlan,
    DishImportResult,
    DishPackageAccess,
    DishPreflight,
    ExpiredShareLinkError,
    InvalidShareLinkError,
    SharingService,
    calculate_shared_dish_nutrition,
)
from app.sharing.payloads import DishSharePayload, SharePayloadLimits
from app.utils.decimal import format_decimal

router = Router(name=__name__)


def created_dish_share_card(
    created: CreatedSharePackage,
    payload: DishSharePayload,
) -> str:
    return f"""📦 <b>Блюдо готово к отправке</b>

{_dish_snapshot_card(payload)}

Ссылка действует до {created.package.expires_at.strftime("%d.%m.%Y")}.
Получатель импортирует блюдо и необходимые ингредиенты."""


def dish_import_preview_card(
    payload: DishSharePayload,
    preflight: DishPreflight,
    plan: DishImportPlan,
) -> str:
    ingredient_status = (
        "разрешены"
        if not plan.unresolved_ingredients
        else f"осталось решить: {len(plan.unresolved_ingredients)}"
    )
    if plan.dish_action is DishImportAction.SKIP:
        dish_status = "блюдо будет пропущено"
    elif plan.dish_action is DishImportAction.UNRESOLVED:
        dish_status = "нужно выбрать действие"
    elif plan.dish_action is DishImportAction.CREATE_COPY:
        dish_status = "будет создана отдельная копия"
    else:
        dish_status = "будет создано"
    warning = (
        "\n\n⚠️ Использование ваших ингредиентов изменит расчёт КБЖУ блюда."
        if plan.uses_changed_existing_ingredients
        and plan.dish_action is not DishImportAction.SKIP
        else ""
    )
    return f"""📦 <b>Вам отправили блюдо</b>

{_dish_snapshot_card(payload)}

Зависимости:
Новых: {preflight.ingredients.new_count}
Уже есть без изменений: {preflight.ingredients.exact_count}
Конфликтов: {preflight.ingredients.conflict_count} ({ingredient_status})

Импорт блюда: {dish_status}{warning}"""


def dish_ingredient_conflict_card(
    preflight: DishPreflight,
    index: int,
) -> str:
    conflict = preflight.ingredients.conflicts[index]
    existing = conflict.existing
    if existing is None:  # pragma: no cover - conflict invariant
        raise RuntimeError("Dish ingredient conflict has no existing ingredient")
    incoming = conflict.incoming
    return f"""⚠️ <b>Для рецепта нужен ингредиент «{escape(incoming.name)}»</b>

Ваш:
{compact_nutrition(existing)}

Полученный:
{compact_nutrition(incoming)}

Конфликт {index + 1} из {preflight.ingredients.conflict_count}."""


def dish_name_conflict_card(preflight: DishPreflight) -> str:
    existing = preflight.existing
    if existing is None:  # pragma: no cover - conflict invariant
        raise RuntimeError("Dish conflict has no existing dish")
    return f"""⚠️ <b>Похожее блюдо уже существует</b>

Полученное: 🍲 <b>{escape(preflight.dish.name)}</b>
Ваше: 🍲 <b>{escape(existing.name)}</b>

Существующий рецепт не будет изменён."""


async def handle_dish_share_start(
    message: Message,
    state: FSMContext,
    current_user: User,
    access: DishPackageAccess,
    service: SharingService,
) -> None:
    if access.is_owner:
        await message.answer(
            "Это ваша ссылка на блюдо. Отправьте её другому пользователю "
            "или отзовите из карточки созданной ссылки.",
            reply_markup=build_dish_import_done_keyboard(None),
        )
        return
    if access.previous_import is not None:
        await message.answer(
            _previous_dish_import_text(access),
            reply_markup=build_dish_import_done_keyboard(None),
        )
        return
    if len(access.payload.dishes) > 1:
        from app.bot.handlers.sharing_dish_batch import (
            handle_dish_batch_share_start,
        )

        await handle_dish_batch_share_start(
            message,
            state,
            current_user,
            access,
            service,
        )
        return
    preflight = await service.preflight_dish(current_user.id, access.payload)
    plan = await service.build_dish_import_plan(
        current_user.id,
        access.payload,
        {},
        None,
    )
    action_token = generate_action_token()
    await state.update_data(
        package_id=access.package.id,
        action_token=action_token,
        ingredient_decisions={},
        dish_decision=None,
    )
    await state.set_state(ShareImportStates.dish_preview)
    await message.answer(
        dish_import_preview_card(access.payload, preflight, plan),
        reply_markup=build_dish_import_preview_keyboard(
            action_token,
            ingredient_conflicts=preflight.ingredients.conflict_count > 0,
            dish_conflict=preflight.conflict_type is not DishConflictType.NEW,
            can_import=plan.can_import,
        ),
    )


@router.callback_query(DishCallback.filter(F.action == "share"))
async def dish_share_callback(
    callback: CallbackQuery,
    callback_data: DishCallback,
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
        created = await service.create_dish_package(
            current_user.id,
            callback_data.dish_id,
        )
        payload = DishSharePayload.model_validate(created.package.payload)
    except (NotFoundError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            created_dish_share_card(created, payload),
            reply_markup=build_created_dish_share_keyboard(
                package_id=created.package.id,
                dish_id=callback_data.dish_id,
                page=callback_data.page,
                deep_link=created.deep_link,
                telegram_share_url=created.telegram_share_url,
            ),
        )


@router.callback_query(DishSharePackageCallback.filter(F.action == "revoke"))
async def dish_share_revoke_callback(
    callback: CallbackQuery,
    callback_data: DishSharePackageCallback,
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
            reply_markup=build_revoked_dish_share_keyboard(
                callback_data.dish_id,
                callback_data.page,
            ),
        )


@router.callback_query(
    ShareImportStates.dish_preview,
    DishImportCallback.filter(F.action == "ingredients"),
)
async def dish_ingredient_conflicts_open(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    context = await _dish_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_dish_error(callback, state, context)
        return
    _, preflight, _ = context
    if not preflight.ingredients.conflicts:
        await _render_dish_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    await state.set_state(ShareImportStates.dish_ingredient_conflict)
    await _edit_ingredient_conflict(callback, state, preflight, 0)


@router.callback_query(
    ShareImportStates.dish_ingredient_conflict,
    DishImportCallback.filter(),
)
async def dish_ingredient_conflict_action(
    callback: CallbackQuery,
    callback_data: DishImportCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    if callback_data.action == "preview":
        await _render_dish_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    context = await _dish_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_dish_error(callback, state, context)
        return
    _, preflight, _ = context
    conflicts = preflight.ingredients.conflicts
    if not conflicts:
        await _render_dish_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    index = min(max(callback_data.index, 0), len(conflicts) - 1)
    if callback_data.action == "abort":
        await state.update_data(dish_decision=DishImportAction.SKIP.value)
        await _render_dish_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    decisions = await _ingredient_decisions(state)
    selected = {
        "reuse": BatchIngredientAction.REUSE,
        "copy": BatchIngredientAction.COPY_WITH_GENERATED_NAME,
    }.get(callback_data.action)
    if selected is not None:
        decisions[conflicts[index].incoming.key] = selected.value
        await state.update_data(ingredient_decisions=decisions)
        if index + 1 < len(conflicts):
            index += 1
    await _edit_ingredient_conflict(callback, state, preflight, index)


@router.callback_query(
    ShareImportStates.dish_preview,
    DishImportCallback.filter(F.action == "dish"),
)
async def dish_name_conflict_open(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    context = await _dish_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_dish_error(callback, state, context)
        return
    _, preflight, _ = context
    if preflight.conflict_type is DishConflictType.NEW:
        await _render_dish_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    await state.set_state(ShareImportStates.dish_name_conflict)
    if callback.message is not None:
        await callback.message.edit_text(
            dish_name_conflict_card(preflight),
            reply_markup=build_dish_name_conflict_keyboard(),
        )


@router.callback_query(
    ShareImportStates.dish_name_conflict,
    DishImportCallback.filter(
        (F.action == DishImportAction.SKIP.value)
        | (F.action == DishImportAction.CREATE_COPY.value)
    ),
)
async def dish_name_conflict_action(
    callback: CallbackQuery,
    callback_data: DishImportCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await state.update_data(dish_decision=callback_data.action)
    await callback.answer()
    await _render_dish_preview(
        callback,
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )


@router.callback_query(
    ShareImportStates.dish_preview,
    ConfirmActionCallback.filter(F.action == DISH_IMPORT_ACTION),
)
async def dish_import_confirm_callback(
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
        result = await service.import_dish(
            package_id,
            current_user.id,
            _valid_ingredient_decisions(data.get("ingredient_decisions")),
            _valid_dish_decision(data.get("dish_decision")),
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        await callback.answer()
        await _show_dish_error(callback, state, error)
        return
    await _show_dish_result(callback, state, result)


@router.callback_query(F.data == DISH_IMPORT_CANCEL)
async def dish_import_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Импорт отменён")
    if callback.message is not None:
        await callback.message.edit_text(
            "Импорт блюда отменён. Данные не изменены.",
            reply_markup=build_dishes_menu_keyboard(),
        )


async def _render_dish_preview(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    context = await _dish_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_dish_error(callback, state, context)
        return
    access, preflight, plan = context
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(ShareImportStates.dish_preview)
    if callback.message is not None:
        await callback.message.edit_text(
            dish_import_preview_card(access.payload, preflight, plan),
            reply_markup=build_dish_import_preview_keyboard(
                action_token,
                ingredient_conflicts=preflight.ingredients.conflict_count > 0,
                dish_conflict=preflight.conflict_type is not DishConflictType.NEW,
                can_import=plan.can_import,
            ),
        )


async def _dish_context(
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> tuple[DishPackageAccess, DishPreflight, DishImportPlan] | ValidationError:
    data = await state.get_data()
    package_id = data.get("package_id")
    if not isinstance(package_id, int):
        return ValidationError("Кнопка устарела. Откройте ссылку заново.")
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        access = await service.get_dish_package(package_id, current_user.id)
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            raise ValidationError("Этот пакет уже был импортирован.")
        preflight = await service.preflight_dish(current_user.id, access.payload)
        plan = await service.build_dish_import_plan(
            current_user.id,
            access.payload,
            _valid_ingredient_decisions(data.get("ingredient_decisions")),
            _valid_dish_decision(data.get("dish_decision")),
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        return error
    return access, preflight, plan


async def _edit_ingredient_conflict(
    callback: CallbackQuery,
    state: FSMContext,
    preflight: DishPreflight,
    index: int,
) -> None:
    if callback.message is None:
        return
    conflicts = preflight.ingredients.conflicts
    index = min(max(index, 0), len(conflicts) - 1)
    decisions = await _ingredient_decisions(state)
    selected_value = decisions.get(conflicts[index].incoming.key)
    selected = (
        BatchIngredientAction(selected_value) if selected_value is not None else None
    )
    await callback.message.edit_text(
        dish_ingredient_conflict_card(preflight, index),
        reply_markup=build_dish_ingredient_conflict_keyboard(
            index=index,
            total=len(conflicts),
            selected=selected,
        ),
    )


async def _show_dish_error(
    callback: CallbackQuery,
    state: FSMContext,
    error: ValidationError,
) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            escape(str(error)),
            reply_markup=build_dishes_menu_keyboard(),
        )


async def _show_dish_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: DishImportResult,
) -> None:
    await state.clear()
    await callback.answer()
    imported = result.import_record
    if result.already_completed:
        prefix = "Этот пакет уже был импортирован."
    elif imported.skipped_dishes_count:
        prefix = "Импорт блюда пропущен по вашему выбору."
    else:
        prefix = "Блюдо импортировано."
    text = f"""{prefix}

Создано ингредиентов: {imported.created_ingredients_count}
Использовано существующих: {imported.reused_ingredients_count}
Создано блюд: {imported.created_dishes_count}
Пропущено блюд: {imported.skipped_dishes_count}"""
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_dish_import_done_keyboard(
                result.dish.dish.id if result.dish is not None else None
            ),
        )


def _dish_snapshot_card(payload: DishSharePayload) -> str:
    dish = payload.dishes[0]
    ingredients = {item.key: item for item in payload.ingredients}
    visible_components = dish.components[:8]
    composition = "\n".join(
        f"• {_preview_name(ingredients[item.ingredient_key].name)} — "
        f"{format_decimal(item.grams)} г"
        for item in visible_components
    )
    if len(dish.components) > len(visible_components):
        composition += f"\n…\nИ ещё: {len(dish.components) - len(visible_components)}"
    nutrition = calculate_shared_dish_nutrition(payload)
    return f"""🍲 <b>{_preview_name(dish.name)}</b>

Состав:
{composition}

{_nutrition_text(nutrition)}"""


def _preview_name(name: str, limit: int = 60) -> str:
    shortened = name if len(name) <= limit else f"{name[: limit - 1]}…"
    return escape(shortened)


def _nutrition_text(nutrition: Any) -> str:
    return f"""Вес рецепта: {format_decimal(nutrition.total_weight)} г

На весь рецепт:
🔥 {format_decimal(nutrition.total.kcal)} ккал
🥩 Б: {format_decimal(nutrition.total.protein)} г
🥑 Ж: {format_decimal(nutrition.total.fat)} г
🍞 У: {format_decimal(nutrition.total.carbs)} г

На 100 г:
🔥 {format_decimal(nutrition.per_100g.kcal)} ккал
🥩 Б: {format_decimal(nutrition.per_100g.protein)} г
🥑 Ж: {format_decimal(nutrition.per_100g.fat)} г
🍞 У: {format_decimal(nutrition.per_100g.carbs)} г"""


def _previous_dish_import_text(access: DishPackageAccess) -> str:
    imported = access.previous_import
    if imported is None:  # pragma: no cover - caller invariant
        raise RuntimeError("Previous dish import is missing")
    if imported.status == ShareImportStatus.PROCESSING:
        return "Этот импорт уже обрабатывается. Повторите проверку чуть позже."
    return f"""Этот пакет уже был импортирован.

Создано ингредиентов: {imported.created_ingredients_count}
Использовано существующих: {imported.reused_ingredients_count}
Создано блюд: {imported.created_dishes_count}
Пропущено блюд: {imported.skipped_dishes_count}"""


async def _ingredient_decisions(state: FSMContext) -> dict[str, str]:
    return _valid_ingredient_decisions(
        (await state.get_data()).get("ingredient_decisions")
    )


def _valid_ingredient_decisions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        BatchIngredientAction.REUSE.value,
        BatchIngredientAction.COPY_WITH_GENERATED_NAME.value,
    }
    return {
        key: action
        for key, action in value.items()
        if isinstance(key, str) and isinstance(action, str) and action in allowed
    }


def _valid_dish_decision(value: Any) -> str | None:
    return (
        value
        if value
        in {
            DishImportAction.CREATE_COPY.value,
            DishImportAction.SKIP.value,
        }
        else None
    )
