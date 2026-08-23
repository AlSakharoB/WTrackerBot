from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.handlers.sharing import compact_nutrition, sharing_service
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.dishes import (
    SHARE_DISHES_SELECT,
    build_dishes_menu_keyboard,
)
from app.bot.keyboards.sharing_dish import build_dish_import_done_keyboard
from app.bot.keyboards.sharing_dish_batch import (
    DISH_BATCH_CANCEL,
    DISH_BATCH_IMPORT_ACTION,
    DISH_SELECTION_CANCEL,
    DISH_SELECTION_CREATE,
    DISH_SELECTION_RESET,
    DISH_SELECTION_SEARCH,
    DishBatchImportCallback,
    DishBatchPackageCallback,
    DishSelectionItemCallback,
    DishSelectionPageCallback,
    build_batch_dish_plan_keyboard,
    build_batch_ingredient_conflict_keyboard,
    build_created_dish_batch_keyboard,
    build_dish_batch_preview_keyboard,
    build_dish_selection_keyboard,
    build_dish_selection_search_keyboard,
)
from app.bot.states.sharing import ShareDishSelectionStates, ShareImportStates
from app.db.models.share import ShareImportStatus
from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.repositories.dishes import DishRepository
from app.repositories.search import SearchRepository
from app.services.action_lock import generate_action_token
from app.services.dishes import DishService
from app.services.search import SearchService
from app.services.sharing import (
    BatchDishImportPlan,
    BatchDishImportResult,
    BatchDishPreflight,
    BatchIngredientAction,
    DishImportAction,
    DishPackageAccess,
    ExpiredShareLinkError,
    InvalidShareLinkError,
    SharingService,
)
from app.sharing.payloads import DishSharePayload, SharePayloadLimits

router = Router(name=__name__)


def created_dish_batch_card(names: list[str], expires_at: str) -> str:
    return f"""📦 <b>Набор блюд готов к отправке</b>

{_names_preview(names)}

Блюд: {len(names)}
Ссылка действует до {expires_at}.
Получатель сам настроит конфликты и подтвердит импорт."""


def dish_batch_preview_card(
    payload: DishSharePayload,
    preflight: BatchDishPreflight,
    plan: BatchDishImportPlan,
) -> str:
    selected_dishes = sum(
        item.action in {DishImportAction.CREATE, DishImportAction.CREATE_COPY}
        for item in plan.dishes
    )
    skipped_dishes = sum(item.action is DishImportAction.SKIP for item in plan.dishes)
    warning = (
        "\n\n⚠️ Использование ваших ингредиентов изменит КБЖУ части блюд."
        if plan.uses_changed_existing_ingredients
        else ""
    )
    return f"""📦 <b>Набор блюд</b>

{_names_preview([dish.name for dish in payload.dishes])}

Блюд: {len(payload.dishes)}
Необходимых ингредиентов: {len(payload.ingredients)}
Новых ингредиентов: {preflight.ingredients.new_count}
Уже есть: {preflight.ingredients.exact_count}
Конфликтов ингредиентов: {preflight.ingredients.conflict_count}
Конфликтов блюд: {preflight.dish_conflict_count}

Будет импортировано блюд: {selected_dishes}
Будет пропущено блюд: {skipped_dishes}
Неразрешённых блюд: {len(plan.unresolved_dishes)}
Неразрешённых зависимостей: {len(plan.unresolved_ingredients)}{warning}"""


async def handle_dish_batch_share_start(
    message: Message,
    state: FSMContext,
    current_user: User,
    access: DishPackageAccess,
    service: SharingService,
) -> None:
    preflight = await service.preflight_dish_batch(current_user.id, access.payload)
    plan = await service.build_dish_batch_import_plan(
        current_user.id,
        access.payload,
        {},
        {},
    )
    action_token = generate_action_token()
    await state.update_data(
        package_id=access.package.id,
        action_token=action_token,
        ingredient_decisions={},
        dish_decisions={},
    )
    await state.set_state(ShareImportStates.dish_batch_preview)
    await message.answer(
        dish_batch_preview_card(access.payload, preflight, plan),
        reply_markup=build_dish_batch_preview_keyboard(
            action_token,
            has_ingredient_conflicts=preflight.ingredients.conflict_count > 0,
            can_import=plan.can_import,
        ),
    )


@router.callback_query(F.data == SHARE_DISHES_SELECT)
async def dish_selection_start(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.clear()
    await state.update_data(selected_ids=[])
    await state.set_state(ShareDishSelectionStates.selecting)
    await callback.answer()
    await _render_selection(callback, state, current_user.id, db_session, 1)


@router.callback_query(
    ShareDishSelectionStates.selecting,
    DishSelectionPageCallback.filter(),
)
async def dish_selection_page(
    callback: CallbackQuery,
    callback_data: DishSelectionPageCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await _render_selection(
        callback,
        state,
        current_user.id,
        db_session,
        callback_data.page,
    )


@router.callback_query(
    ShareDishSelectionStates.selecting,
    DishSelectionItemCallback.filter(),
)
async def dish_selection_toggle(
    callback: CallbackQuery,
    callback_data: DishSelectionItemCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    share_payload_limits: SharePayloadLimits,
) -> None:
    try:
        await DishService(DishRepository(db_session)).get(
            current_user.id,
            callback_data.dish_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    selected = await _selected_ids(state)
    if callback_data.dish_id in selected:
        selected.remove(callback_data.dish_id)
    elif len(selected) >= share_payload_limits.max_items:
        await callback.answer(
            f"Можно выбрать не более {share_payload_limits.max_items} блюд.",
            show_alert=True,
        )
        return
    else:
        selected.append(callback_data.dish_id)
    await state.update_data(selected_ids=selected)
    await callback.answer(f"Выбрано: {len(selected)}")
    if callback_data.page == 0:
        await _refresh_search_markup(callback, set(selected))
        return
    await _render_selection(
        callback,
        state,
        current_user.id,
        db_session,
        callback_data.page,
    )


@router.callback_query(
    ShareDishSelectionStates.selecting,
    F.data == DISH_SELECTION_SEARCH,
)
async def dish_selection_search(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(ShareDishSelectionStates.wait_search_query)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название или часть названия блюда:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data=DISH_SELECTION_CANCEL,
                        )
                    ]
                ]
            ),
        )


@router.message(ShareDishSelectionStates.wait_search_query)
async def dish_selection_search_query(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        results = await SearchService(SearchRepository(db_session)).search_dishes(
            current_user.id,
            message.text or "",
        )
    except ValidationError as error:
        await message.answer(str(error))
        return
    await state.set_state(ShareDishSelectionStates.selecting)
    selected = set(await _selected_ids(state))
    text = "🔎 <b>Результаты поиска</b>"
    if not results:
        text += "\n\nНичего похожего не найдено."
    await message.answer(
        text,
        reply_markup=build_dish_selection_search_keyboard(results, selected),
    )


@router.callback_query(
    ShareDishSelectionStates.selecting,
    F.data == DISH_SELECTION_RESET,
)
async def dish_selection_reset(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.update_data(selected_ids=[])
    await callback.answer("Выбор сброшен")
    await _render_selection(callback, state, current_user.id, db_session, 1)


@router.callback_query(
    ShareDishSelectionStates.selecting,
    F.data == DISH_SELECTION_CREATE,
)
async def dish_selection_create(
    callback: CallbackQuery,
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
        created = await service.create_dish_batch_package(
            current_user.id,
            await _selected_ids(state),
        )
        payload = DishSharePayload.model_validate(created.package.payload)
    except (NotFoundError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            created_dish_batch_card(
                [dish.name for dish in payload.dishes],
                created.package.expires_at.strftime("%d.%m.%Y"),
            ),
            reply_markup=build_created_dish_batch_keyboard(
                package_id=created.package.id,
                deep_link=created.deep_link,
                telegram_share_url=created.telegram_share_url,
            ),
        )


@router.callback_query(F.data == DISH_SELECTION_CANCEL)
async def dish_selection_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Действие отменено")
    if callback.message is not None:
        await callback.message.edit_text(
            "🍲 <b>Блюда</b>\n\nСобирайте рецепты из своих ингредиентов.",
            reply_markup=build_dishes_menu_keyboard(),
        )


@router.callback_query(DishBatchPackageCallback.filter(F.action == "revoke"))
async def dish_batch_revoke(
    callback: CallbackQuery,
    callback_data: DishBatchPackageCallback,
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
            reply_markup=build_dishes_menu_keyboard(),
        )


@router.callback_query(
    ShareImportStates.dish_batch_preview,
    DishBatchImportCallback.filter(F.action == "ingredients"),
)
async def dish_batch_ingredients_open(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    context = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_error(callback, state, context)
        return
    _, preflight, _ = context
    if not preflight.ingredients.conflicts:
        await _render_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    await state.set_state(ShareImportStates.dish_batch_ingredient_conflict)
    await _edit_ingredient_conflict(callback, state, preflight, 0)


@router.callback_query(
    ShareImportStates.dish_batch_ingredient_conflict,
    DishBatchImportCallback.filter(),
)
async def dish_batch_ingredient_action(
    callback: CallbackQuery,
    callback_data: DishBatchImportCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    if callback_data.action == "preview":
        await _render_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    context = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_error(callback, state, context)
        return
    _, preflight, _ = context
    conflicts = preflight.ingredients.conflicts
    index = min(max(callback_data.index, 0), len(conflicts) - 1)
    decisions = await _ingredient_decisions(state)
    action = {
        "reuse": BatchIngredientAction.REUSE,
        "copy": BatchIngredientAction.COPY_WITH_GENERATED_NAME,
    }.get(callback_data.action)
    if action is not None:
        decisions[conflicts[index].incoming.key] = action.value
        await state.update_data(ingredient_decisions=decisions)
        if index + 1 < len(conflicts):
            index += 1
    await _edit_ingredient_conflict(callback, state, preflight, index)


@router.callback_query(
    ShareImportStates.dish_batch_preview,
    DishBatchImportCallback.filter(F.action == "dishes"),
)
async def dish_batch_plan_open(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    context = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_error(callback, state, context)
        return
    _, _, plan = context
    await state.set_state(ShareImportStates.dish_batch_dish_plan)
    await _edit_dish_plan(callback, plan, 0)


@router.callback_query(
    ShareImportStates.dish_batch_dish_plan,
    DishBatchImportCallback.filter(),
)
async def dish_batch_plan_action(
    callback: CallbackQuery,
    callback_data: DishBatchImportCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    if callback_data.action == "preview":
        await _render_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    context = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_error(callback, state, context)
        return
    _, _, plan = context
    index = min(max(callback_data.index, 0), len(plan.dishes) - 1)
    decisions = await _dish_decisions(state)
    dish_key = plan.dishes[index].preflight.dish.key
    if callback_data.action == "dish_create":
        decisions.pop(dish_key, None)
    elif callback_data.action == "dish_copy":
        decisions[dish_key] = DishImportAction.CREATE_COPY.value
    elif callback_data.action == "dish_skip":
        decisions[dish_key] = DishImportAction.SKIP.value
    if callback_data.action in {"dish_create", "dish_copy", "dish_skip"}:
        await state.update_data(dish_decisions=decisions)
        if index + 1 < len(plan.dishes):
            index += 1
        context = await _batch_context(
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        if isinstance(context, ValidationError):
            await _show_error(callback, state, context)
            return
        _, _, plan = context
    await _edit_dish_plan(callback, plan, index)


@router.callback_query(
    ShareImportStates.dish_batch_preview,
    ConfirmActionCallback.filter(F.action == DISH_BATCH_IMPORT_ACTION),
)
async def dish_batch_import_confirm(
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
        result = await service.import_dish_batch(
            package_id,
            current_user.id,
            _valid_ingredient_decisions(data.get("ingredient_decisions")),
            _valid_dish_decisions(data.get("dish_decisions")),
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        await callback.answer()
        await _show_error(callback, state, error)
        return
    await _show_result(callback, state, result)


@router.callback_query(F.data == DISH_BATCH_CANCEL)
async def dish_batch_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Импорт отменён")
    if callback.message is not None:
        await callback.message.edit_text(
            "Импорт набора отменён. Данные не изменены.",
            reply_markup=build_dishes_menu_keyboard(),
        )


async def _render_selection(
    callback: CallbackQuery,
    state: FSMContext,
    user_id: int,
    session: AsyncSession,
    page_number: int,
) -> None:
    if callback.message is None:
        return
    page = await DishService(DishRepository(session)).list_page(user_id, page_number)
    selected = set(await _selected_ids(state))
    text = f"📤 <b>Выберите блюда</b>\n\nВыбрано: {len(selected)}"
    if page.total == 0:
        text += "\n\nУ вас пока нет блюд."
    await callback.message.edit_text(
        text,
        reply_markup=build_dish_selection_keyboard(page, selected),
    )


async def _render_preview(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    context = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if isinstance(context, ValidationError):
        await _show_error(callback, state, context)
        return
    access, preflight, plan = context
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(ShareImportStates.dish_batch_preview)
    if callback.message is not None:
        await callback.message.edit_text(
            dish_batch_preview_card(access.payload, preflight, plan),
            reply_markup=build_dish_batch_preview_keyboard(
                action_token,
                has_ingredient_conflicts=preflight.ingredients.conflict_count > 0,
                can_import=plan.can_import,
            ),
        )


async def _batch_context(
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> (
    tuple[DishPackageAccess, BatchDishPreflight, BatchDishImportPlan] | ValidationError
):
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
        preflight = await service.preflight_dish_batch(current_user.id, access.payload)
        plan = await service.build_dish_batch_import_plan(
            current_user.id,
            access.payload,
            _valid_ingredient_decisions(data.get("ingredient_decisions")),
            _valid_dish_decisions(data.get("dish_decisions")),
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        return error
    return access, preflight, plan


async def _edit_ingredient_conflict(
    callback: CallbackQuery,
    state: FSMContext,
    preflight: BatchDishPreflight,
    index: int,
) -> None:
    if callback.message is None:
        return
    conflicts = preflight.ingredients.conflicts
    index = min(max(index, 0), len(conflicts) - 1)
    conflict = conflicts[index]
    existing = conflict.existing
    if existing is None:  # pragma: no cover - conflict invariant
        raise RuntimeError("Batch dish conflict has no existing ingredient")
    decisions = await _ingredient_decisions(state)
    selected_value = decisions.get(conflict.incoming.key)
    selected = (
        BatchIngredientAction(selected_value) if selected_value is not None else None
    )
    text = f"""⚠️ <b>Общий ингредиент «{escape(conflict.incoming.name)}»</b>

Ваш:
{compact_nutrition(existing)}

Полученный:
{compact_nutrition(conflict.incoming)}

Решение применяется ко всем блюдам набора."""
    await callback.message.edit_text(
        text,
        reply_markup=build_batch_ingredient_conflict_keyboard(
            index=index,
            total=len(conflicts),
            selected=selected,
        ),
    )


async def _edit_dish_plan(
    callback: CallbackQuery,
    plan: BatchDishImportPlan,
    index: int,
) -> None:
    if callback.message is None:
        return
    index = min(max(index, 0), len(plan.dishes) - 1)
    item = plan.dishes[index]
    existing_text = (
        f"\nПохожее у вас: 🍲 <b>{escape(item.preflight.existing.name)}</b>"
        if item.preflight.existing is not None
        else ""
    )
    text = f"""🍲 <b>{escape(item.preflight.dish.name)}</b>
{existing_text}

Выберите действие для блюда {index + 1} из {len(plan.dishes)}."""
    await callback.message.edit_text(
        text,
        reply_markup=build_batch_dish_plan_keyboard(
            index=index,
            total=len(plan.dishes),
            conflict_type=item.preflight.conflict_type,
            selected=item.action,
        ),
    )


async def _show_error(
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


async def _show_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: BatchDishImportResult,
) -> None:
    await state.clear()
    await callback.answer()
    imported = result.import_record
    prefix = (
        "Этот набор уже был импортирован."
        if result.already_completed
        else "✅ Набор импортирован"
    )
    text = f"""{prefix}

Блюд добавлено: {imported.created_dishes_count}
Блюд пропущено: {imported.skipped_dishes_count}
Ингредиентов создано: {imported.created_ingredients_count}
Ингредиентов использовано существующих: {imported.reused_ingredients_count}"""
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_dish_import_done_keyboard(None),
        )


async def _refresh_search_markup(
    callback: CallbackQuery,
    selected_ids: set[int],
) -> None:
    if callback.message is None or callback.message.reply_markup is None:
        return
    markup = callback.message.reply_markup.model_copy(deep=True)
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data is None or not button.callback_data.startswith(
                "shdsi:"
            ):
                continue
            parsed = DishSelectionItemCallback.unpack(button.callback_data)
            marker = "☑️" if parsed.dish_id in selected_ids else "⬜"
            button.text = f"{marker} {button.text[2:].lstrip()}"
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == DISH_SELECTION_CREATE:
                button.text = f"🔗 Создать ссылку ({len(selected_ids)})"
    await callback.message.edit_reply_markup(reply_markup=markup)


async def _selected_ids(state: FSMContext) -> list[int]:
    value = (await state.get_data()).get("selected_ids", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


async def _ingredient_decisions(state: FSMContext) -> dict[str, str]:
    return _valid_ingredient_decisions(
        (await state.get_data()).get("ingredient_decisions")
    )


async def _dish_decisions(state: FSMContext) -> dict[str, str]:
    return _valid_dish_decisions((await state.get_data()).get("dish_decisions"))


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


def _valid_dish_decisions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        DishImportAction.CREATE_COPY.value,
        DishImportAction.SKIP.value,
    }
    return {
        key: action
        for key, action in value.items()
        if isinstance(key, str) and isinstance(action, str) and action in allowed
    }


def _names_preview(names: list[str]) -> str:
    visible = names if len(names) <= 5 else names[:3]
    lines = [f"• {_display_name(name)}" for name in visible]
    if len(names) > len(visible):
        lines.extend(("…", f"И ещё: {len(names) - len(visible)}"))
    return "\n".join(lines)


def _display_name(name: str, limit: int = 60) -> str:
    shortened = name if len(name) <= limit else f"{name[: limit - 1]}…"
    return escape(shortened)
