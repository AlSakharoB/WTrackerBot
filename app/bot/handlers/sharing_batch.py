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
from app.bot.keyboards.ingredients import (
    SHARE_INGREDIENTS_SELECT,
    build_ingredients_menu_keyboard,
)
from app.bot.keyboards.sharing import (
    build_import_cancelled_keyboard,
    build_import_done_keyboard,
)
from app.bot.keyboards.sharing_batch import (
    SHARE_BATCH_IMPORT_ACTION,
    SHARE_SELECTION_CANCEL,
    SHARE_SELECTION_CREATE,
    SHARE_SELECTION_RESET,
    SHARE_SELECTION_SEARCH,
    BatchConflictCallback,
    BatchSharePackageCallback,
    ShareSelectionItemCallback,
    ShareSelectionPageCallback,
    build_batch_conflict_keyboard,
    build_batch_preview_keyboard,
    build_created_batch_share_keyboard,
    build_selection_keyboard,
    build_selection_search_keyboard,
)
from app.bot.states.sharing import (
    ShareImportStates,
    ShareIngredientSelectionStates,
)
from app.db.models.share import ShareImportStatus
from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.repositories.search import SearchRepository
from app.services.action_lock import generate_action_token
from app.services.ingredients import IngredientService
from app.services.search import SearchService
from app.services.sharing import (
    BatchIngredientAction,
    BatchIngredientImportResult,
    BatchIngredientPreflight,
    ExpiredShareLinkError,
    IngredientPackageAccess,
    InvalidShareLinkError,
    SharingService,
)
from app.sharing.payloads import SharePayloadLimits

router = Router(name=__name__)


def batch_created_card(names: list[str], expires_at: str) -> str:
    return f"""📦 <b>Набор ингредиентов готов к отправке</b>

{_names_preview(names)}

Всего: {len(names)}
Ссылка действует до {expires_at}.
Получатель сам подтвердит импорт."""


def batch_import_preview_card(
    names: list[str],
    preflight: BatchIngredientPreflight,
    decisions: dict[str, str],
) -> str:
    resolved = sum(item.incoming.key in decisions for item in preflight.conflicts)
    return f"""📦 <b>Вам отправили набор ингредиентов</b>

{_names_preview(names)}

Всего: {len(names)}
Новых: {preflight.new_count}
Уже есть без изменений: {preflight.exact_count}
Конфликтов: {preflight.conflict_count}
Решения по конфликтам: {resolved}/{preflight.conflict_count}

По умолчанию конфликтующие ингредиенты будут пропущены."""


def batch_conflict_card(
    preflight: BatchIngredientPreflight,
    index: int,
) -> str:
    conflict = preflight.conflicts[index]
    existing = conflict.existing
    if existing is None:  # pragma: no cover - conflict invariant
        raise RuntimeError("Batch conflict has no existing ingredient")
    incoming = conflict.incoming
    return f"""⚠️ <b>Конфликт {index + 1} из {preflight.conflict_count}</b>

Ваш:
🥕 <b>{escape(existing.name)}</b>
{compact_nutrition(existing)}

Полученный:
🥕 <b>{escape(incoming.name)}</b>
{compact_nutrition(incoming)}

Выберите действие:"""


async def handle_batch_ingredient_access(
    message: Message,
    state: FSMContext,
    current_user: User,
    access: IngredientPackageAccess,
    service: SharingService,
) -> None:
    preflight = await service.preflight_ingredient_batch(
        current_user.id, access.payload
    )
    action_token = generate_action_token()
    await state.update_data(
        package_id=access.package.id,
        action_token=action_token,
        conflict_decisions={},
    )
    await state.set_state(ShareImportStates.batch_preview)
    await message.answer(
        batch_import_preview_card(
            [item.name for item in access.payload.ingredients],
            preflight,
            {},
        ),
        reply_markup=build_batch_preview_keyboard(
            action_token,
            has_conflicts=preflight.conflict_count > 0,
        ),
    )


@router.callback_query(F.data == SHARE_INGREDIENTS_SELECT)
async def share_selection_start(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.clear()
    await state.update_data(selected_ids=[])
    await state.set_state(ShareIngredientSelectionStates.selecting)
    await callback.answer()
    await _render_selection_page(callback, db_session, current_user.id, state, 1)


@router.callback_query(
    ShareIngredientSelectionStates.selecting,
    ShareSelectionPageCallback.filter(),
)
async def share_selection_page(
    callback: CallbackQuery,
    callback_data: ShareSelectionPageCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await _render_selection_page(
        callback, db_session, current_user.id, state, callback_data.page
    )


@router.callback_query(
    ShareIngredientSelectionStates.selecting,
    ShareSelectionItemCallback.filter(),
)
async def share_selection_toggle(
    callback: CallbackQuery,
    callback_data: ShareSelectionItemCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    share_payload_limits: SharePayloadLimits,
) -> None:
    ingredient_service = _ingredient_service(db_session)
    try:
        await ingredient_service.get(current_user.id, callback_data.ingredient_id)
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    selected_ids = await _selected_ids(state)
    if callback_data.ingredient_id in selected_ids:
        selected_ids.remove(callback_data.ingredient_id)
    elif len(selected_ids) >= share_payload_limits.max_items:
        await callback.answer(
            f"Можно выбрать не более {share_payload_limits.max_items} ингредиентов.",
            show_alert=True,
        )
        return
    else:
        selected_ids.append(callback_data.ingredient_id)
    await state.update_data(selected_ids=selected_ids)
    await callback.answer(f"Выбрано: {len(selected_ids)}")
    if callback_data.page == 0:
        await _refresh_search_markup(callback, set(selected_ids))
        return
    await _render_selection_page(
        callback, db_session, current_user.id, state, callback_data.page
    )


@router.callback_query(
    ShareIngredientSelectionStates.selecting,
    F.data == SHARE_SELECTION_SEARCH,
)
async def share_selection_search(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(ShareIngredientSelectionStates.wait_search_query)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название или часть названия ингредиента:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data=SHARE_SELECTION_CANCEL,
                        )
                    ]
                ]
            ),
        )


@router.message(ShareIngredientSelectionStates.wait_search_query)
async def share_selection_search_query(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        results = await SearchService(SearchRepository(db_session)).search_ingredients(
            current_user.id, message.text or ""
        )
    except ValidationError as error:
        await message.answer(str(error))
        return
    await state.set_state(ShareIngredientSelectionStates.selecting)
    selected_ids = set(await _selected_ids(state))
    text = "🔎 <b>Результаты поиска</b>"
    if not results:
        text += "\n\nНичего похожего не найдено."
    await message.answer(
        text,
        reply_markup=build_selection_search_keyboard(results, selected_ids),
    )


@router.callback_query(
    ShareIngredientSelectionStates.selecting,
    F.data == SHARE_SELECTION_RESET,
)
async def share_selection_reset(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.update_data(selected_ids=[])
    await callback.answer("Выбор сброшен")
    await _render_selection_page(callback, db_session, current_user.id, state, 1)


@router.callback_query(
    ShareIngredientSelectionStates.selecting,
    F.data == SHARE_SELECTION_CREATE,
)
async def share_selection_create(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    selected_ids = await _selected_ids(state)
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        created = await service.create_ingredient_batch_package(
            current_user.id, selected_ids
        )
    except (NotFoundError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    names = [str(item["name"]) for item in created.package.payload["ingredients"]]
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            batch_created_card(
                names,
                created.package.expires_at.strftime("%d.%m.%Y"),
            ),
            reply_markup=build_created_batch_share_keyboard(
                package_id=created.package.id,
                deep_link=created.deep_link,
                telegram_share_url=created.telegram_share_url,
            ),
        )


@router.callback_query(F.data == SHARE_SELECTION_CANCEL)
async def share_selection_cancel(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await callback.answer("Действие отменено")
    if callback.message is not None:
        await callback.message.edit_text(
            "🥕 <b>Ингредиенты</b>\n\nСоздавайте и управляйте своими продуктами.",
            reply_markup=build_ingredients_menu_keyboard(),
        )


@router.callback_query(BatchSharePackageCallback.filter(F.action == "revoke"))
async def batch_share_revoke(
    callback: CallbackQuery,
    callback_data: BatchSharePackageCallback,
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
            reply_markup=build_import_cancelled_keyboard(),
        )


@router.callback_query(
    ShareImportStates.batch_preview,
    BatchConflictCallback.filter(F.action == "open"),
)
async def batch_conflicts_open(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    await _render_conflict(
        callback,
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
        0,
    )


@router.callback_query(
    ShareImportStates.batch_conflict,
    BatchConflictCallback.filter(),
)
async def batch_conflict_action(
    callback: CallbackQuery,
    callback_data: BatchConflictCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    await callback.answer()
    if callback_data.action == "done":
        await _render_batch_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    access, preflight, error = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if error is not None or access is None or preflight is None:
        await _show_batch_error(callback, state, error or ValidationError("Ошибка"))
        return
    if not preflight.conflicts:
        await _render_batch_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    index = min(max(callback_data.index, 0), len(preflight.conflicts) - 1)
    decisions = await _conflict_decisions(state)
    action_map = {
        "skip": BatchIngredientAction.SKIP,
        "reuse": BatchIngredientAction.REUSE,
        "copy": BatchIngredientAction.COPY_WITH_GENERATED_NAME,
    }
    selected = action_map.get(callback_data.action)
    if selected is not None:
        decisions[preflight.conflicts[index].incoming.key] = selected.value
        await state.update_data(conflict_decisions=decisions)
        if index + 1 < len(preflight.conflicts):
            index += 1
    await _edit_conflict(callback, state, preflight, index)


@router.callback_query(
    ShareImportStates.batch_preview,
    ConfirmActionCallback.filter(F.action == SHARE_BATCH_IMPORT_ACTION),
)
async def batch_import_confirm(
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
    decisions = _valid_decisions(data.get("conflict_decisions"))
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        result = await service.import_ingredient_batch(
            package_id, current_user.id, decisions
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        await _show_batch_error(callback, state, error)
        return
    await _show_batch_result(callback, state, result)


async def _render_selection_page(
    callback: CallbackQuery,
    db_session: AsyncSession,
    user_id: int,
    state: FSMContext,
    page_number: int,
) -> None:
    if callback.message is None:
        return
    page = await _ingredient_service(db_session).list_page(user_id, page_number)
    selected = set(await _selected_ids(state))
    text = f"📤 <b>Выберите ингредиенты</b>\n\nВыбрано: {len(selected)}"
    if page.total == 0:
        text += "\n\nУ вас пока нет ингредиентов."
    await callback.message.edit_text(
        text,
        reply_markup=build_selection_keyboard(page, selected),
    )


async def _render_conflict(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
    index: int,
) -> None:
    access, preflight, error = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if error is not None or access is None or preflight is None:
        await _show_batch_error(callback, state, error or ValidationError("Ошибка"))
        return
    if not preflight.conflicts:
        await _render_batch_preview(
            callback,
            state,
            current_user,
            db_session,
            bot_username,
            share_link_ttl_days,
            share_payload_limits,
        )
        return
    await state.set_state(ShareImportStates.batch_conflict)
    await _edit_conflict(callback, state, preflight, index)


async def _edit_conflict(
    callback: CallbackQuery,
    state: FSMContext,
    preflight: BatchIngredientPreflight,
    index: int,
) -> None:
    if callback.message is None:
        return
    index = min(max(index, 0), len(preflight.conflicts) - 1)
    decisions = await _conflict_decisions(state)
    selected = BatchIngredientAction(
        decisions.get(
            preflight.conflicts[index].incoming.key,
            BatchIngredientAction.SKIP.value,
        )
    )
    await callback.message.edit_text(
        batch_conflict_card(preflight, index),
        reply_markup=build_batch_conflict_keyboard(
            index=index,
            total=len(preflight.conflicts),
            selected=selected,
        ),
    )


async def _render_batch_preview(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> None:
    access, preflight, error = await _batch_context(
        state,
        current_user,
        db_session,
        bot_username,
        share_link_ttl_days,
        share_payload_limits,
    )
    if error is not None or access is None or preflight is None:
        await _show_batch_error(callback, state, error or ValidationError("Ошибка"))
        return
    action_token = generate_action_token()
    decisions = await _conflict_decisions(state)
    await state.update_data(action_token=action_token)
    await state.set_state(ShareImportStates.batch_preview)
    if callback.message is not None:
        await callback.message.edit_text(
            batch_import_preview_card(
                [item.name for item in access.payload.ingredients],
                preflight,
                decisions,
            ),
            reply_markup=build_batch_preview_keyboard(
                action_token,
                has_conflicts=preflight.conflict_count > 0,
            ),
        )


async def _batch_context(
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    bot_username: str | None,
    share_link_ttl_days: int,
    share_payload_limits: SharePayloadLimits,
) -> tuple[
    IngredientPackageAccess | None,
    BatchIngredientPreflight | None,
    ValidationError | None,
]:
    data = await state.get_data()
    package_id = data.get("package_id")
    if not isinstance(package_id, int):
        return None, None, ValidationError("Кнопка устарела. Откройте ссылку заново.")
    service = sharing_service(
        db_session,
        bot_username=bot_username,
        share_link_ttl_days=share_link_ttl_days,
        share_payload_limits=share_payload_limits,
    )
    try:
        access = await service.get_ingredient_package(package_id, current_user.id)
        if access.is_owner:
            raise ValidationError("Нельзя импортировать собственную ссылку.")
        if (
            access.previous_import is not None
            and access.previous_import.status == ShareImportStatus.COMPLETED
        ):
            raise ValidationError("Этот пакет уже был импортирован.")
        preflight = await service.preflight_ingredient_batch(
            current_user.id, access.payload
        )
    except (InvalidShareLinkError, ExpiredShareLinkError, ValidationError) as error:
        return None, None, error
    return access, preflight, None


async def _show_batch_error(
    callback: CallbackQuery,
    state: FSMContext,
    error: ValidationError,
) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            escape(str(error)), reply_markup=build_import_cancelled_keyboard()
        )


async def _show_batch_result(
    callback: CallbackQuery,
    state: FSMContext,
    result: BatchIngredientImportResult,
) -> None:
    await state.clear()
    await callback.answer()
    imported = result.import_record
    prefix = (
        "Этот пакет уже был импортирован."
        if result.already_completed
        else "Импорт завершён."
    )
    text = f"""{prefix}

Создано: {imported.created_ingredients_count}
Использовано существующих: {imported.reused_ingredients_count}
Пропущено: {imported.skipped_ingredients_count}"""
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_import_done_keyboard(),
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
                "shsi:"
            ):
                continue
            parsed = ShareSelectionItemCallback.unpack(button.callback_data)
            marker = "☑️" if parsed.ingredient_id in selected_ids else "⬜"
            button.text = f"{marker} {button.text[2:].lstrip()}"
    for row in markup.inline_keyboard:
        for button in row:
            if button.callback_data == SHARE_SELECTION_CREATE:
                button.text = f"🔗 Создать ссылку ({len(selected_ids)})"
    await callback.message.edit_reply_markup(reply_markup=markup)


async def _selected_ids(state: FSMContext) -> list[int]:
    value = (await state.get_data()).get("selected_ids", [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int)]


async def _conflict_decisions(state: FSMContext) -> dict[str, str]:
    return _valid_decisions((await state.get_data()).get("conflict_decisions"))


def _valid_decisions(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    allowed = {
        BatchIngredientAction.REUSE.value,
        BatchIngredientAction.COPY_WITH_GENERATED_NAME.value,
        BatchIngredientAction.SKIP.value,
    }
    return {
        key: action
        for key, action in value.items()
        if isinstance(key, str) and isinstance(action, str) and action in allowed
    }


def _ingredient_service(session: AsyncSession) -> IngredientService:
    from app.repositories.ingredients import IngredientRepository

    return IngredientService(IngredientRepository(session))


def _names_preview(names: list[str]) -> str:
    visible = names if len(names) <= 5 else names[:3]
    lines = [f"• {escape(name)}" for name in visible]
    if len(names) > 5:
        lines.extend(("…", f"И ещё: {len(names) - len(visible)}"))
    return "\n".join(lines)
