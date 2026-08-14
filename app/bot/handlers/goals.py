from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import GOAL_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.goals import (
    GOAL_BACK_MAIN,
    GOAL_CREATE,
    GOAL_FLOW_CANCEL,
    GOAL_MENU,
    GoalActionCallback,
    GoalDateCallback,
    build_achieved_goal_keyboard,
    build_active_goal_keyboard,
    build_empty_goal_keyboard,
    build_goal_action_confirmation_keyboard,
    build_goal_cancel_keyboard,
    build_goal_date_keyboard,
    build_goal_save_keyboard,
    build_goal_without_progress_keyboard,
)
from app.bot.keyboards.main import GOAL_BUTTON
from app.bot.states.goals import GoalCreateStates
from app.db.models.user import User
from app.exceptions import AppError, ValidationError
from app.repositories.goals import GoalRepository
from app.repositories.weights import WeightRepository
from app.services.action_lock import generate_action_token
from app.services.goals import GoalDetails, GoalService, parse_target_date
from app.services.weights import parse_weight
from app.utils.decimal import format_decimal
from app.utils.formatting import format_date
from app.utils.progress import build_progress_bar

router = Router(name=__name__)


def goal_service(session: AsyncSession) -> GoalService:
    return GoalService(GoalRepository(session), WeightRepository(session))


def goal_card(details: GoalDetails) -> str:
    goal = details.goal
    current = details.current_weight
    progress = details.progress
    deadline = format_date(goal.target_date) if goal.target_date else "не указан"
    if progress is not None and progress.achieved:
        title = "🎯 <b>Цель достигнута!</b>"
    elif goal.start_weight_kg is None:
        target = format_decimal(goal.target_weight_kg)
        title = f"🎯 <b>Цель: {target} кг</b>"
    else:
        title = "🎯 <b>Цель по весу</b>"
    lines = [
        title,
        "",
    ]
    if goal.start_weight_kg is not None:
        lines.append(f"Старт: {format_decimal(goal.start_weight_kg)} кг")
    if current is not None:
        lines.append(f"Сейчас: {format_decimal(current.weight_kg)} кг")
    if goal.start_weight_kg is not None:
        lines.append(f"Цель: {format_decimal(goal.target_weight_kg)} кг")

    if progress is not None:
        percentage = format_decimal(progress.percentage, 0)
        if goal.target_weight_kg < goal.start_weight_kg:
            change_label = "Сброшено"
        elif goal.target_weight_kg > goal.start_weight_kg:
            change_label = "Набрано"
        else:
            change_label = "Изменение"
        lines.extend(
            [
                "",
                f"Прогресс: {percentage}%",
                "",
                f"{build_progress_bar(progress.percentage)} {percentage}%",
                "",
                f"{change_label}: {format_decimal(progress.completed_kg)} кг",
                f"Осталось: {format_decimal(progress.remaining_kg)} кг",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Чтобы считать прогресс,",
                "добавьте текущий вес.",
            ]
        )
    lines.extend(["", f"Срок: {deadline}"])
    return "\n".join(lines)


def goal_confirmation_text(
    *,
    target_weight_kg: Decimal,
    target_date: date | None,
    start_weight_kg: Decimal | None,
    replace_existing: bool,
) -> str:
    deadline = format_date(target_date) if target_date else "без срока"
    start = (
        f"{format_decimal(start_weight_kg)} кг"
        if start_weight_kg is not None
        else "нет измерения"
    )
    lines = [
        "Создать цель?",
        "",
        f"🎯 Целевой вес: <b>{format_decimal(target_weight_kg)} кг</b>",
        f"Стартовый вес: {start}",
        f"Срок: {deadline}",
    ]
    if replace_existing:
        lines.extend(["", "Текущая активная цель будет отменена и заменена."])
    return "\n".join(lines)


async def show_goal(
    message: Message,
    state: FSMContext,
    service: GoalService,
    user_id: int,
    *,
    edit: bool,
) -> None:
    details = await service.get_active(user_id)
    await state.clear()
    if details is None:
        text = "🎯 <b>Цель</b>\n\nУ вас пока нет активной цели."
        markup = build_empty_goal_keyboard()
    else:
        text = goal_card(details)
        if details.progress is None:
            markup = build_goal_without_progress_keyboard(details.goal.id)
        elif details.progress.achieved:
            markup = build_achieved_goal_keyboard(details.goal.id)
        else:
            markup = build_active_goal_keyboard(details.goal.id)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def show_goal_confirmation(
    message: Message,
    state: FSMContext,
    service: GoalService,
    user_id: int,
    target_date: date | None,
) -> None:
    data = await state.get_data()
    if "target_weight_kg" not in data:
        await state.clear()
        await message.edit_text("Данные устарели. Начните создание заново.")
        return
    target_weight_kg = Decimal(str(data["target_weight_kg"]))
    active = await service.get_active(user_id)
    current = (
        active.current_weight
        if active is not None
        else await service.get_current_weight(user_id)
    )
    replace_existing = active is not None
    action_token = generate_action_token()
    await state.update_data(
        target_date=target_date.isoformat() if target_date else None,
        replace_existing=replace_existing,
        action_token=action_token,
    )
    await state.set_state(GoalCreateStates.confirm)
    await message.edit_text(
        goal_confirmation_text(
            target_weight_kg=target_weight_kg,
            target_date=target_date,
            start_weight_kg=current.weight_kg if current is not None else None,
            replace_existing=replace_existing,
        ),
        reply_markup=build_goal_save_keyboard(replace_existing, action_token),
    )


@router.message(Command("goal"))
@router.message(F.text == GOAL_BUTTON)
async def goal_menu_handler(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await show_goal(
        message,
        state,
        goal_service(db_session),
        current_user.id,
        edit=False,
    )


@router.callback_query(F.data == GOAL_MENU)
async def goal_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_goal(
            callback.message,
            state,
            goal_service(db_session),
            current_user.id,
            edit=True,
        )


@router.callback_query(F.data == GOAL_CREATE)
async def goal_create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(GoalCreateStates.wait_target_weight)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите целевой вес в килограммах:",
            reply_markup=build_goal_cancel_keyboard(),
        )


@router.callback_query(GoalActionCallback.filter(F.action == "replace"))
async def goal_replace_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(GoalCreateStates.wait_target_weight)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новый целевой вес в килограммах:",
            reply_markup=build_goal_cancel_keyboard(),
        )


@router.message(GoalCreateStates.wait_target_weight)
async def goal_target_weight_message(message: Message, state: FSMContext) -> None:
    try:
        target_weight_kg = parse_weight(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_goal_cancel_keyboard())
        return
    await state.update_data(target_weight_kg=str(target_weight_kg))
    await state.set_state(GoalCreateStates.choose_target_date)
    await message.answer("Укажите срок:", reply_markup=build_goal_date_keyboard())


@router.callback_query(GoalDateCallback.filter())
async def goal_date_callback(
    callback: CallbackQuery,
    callback_data: GoalDateCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if callback_data.mode == "custom":
        await state.set_state(GoalCreateStates.wait_target_date)
        await callback.message.edit_text(
            "Введите срок в формате ДД.ММ.ГГГГ:",
            reply_markup=build_goal_cancel_keyboard(),
        )
        return
    await show_goal_confirmation(
        callback.message,
        state,
        goal_service(db_session),
        current_user.id,
        None,
    )


@router.message(GoalCreateStates.wait_target_date)
async def goal_target_date_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        target_date = parse_target_date(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_goal_cancel_keyboard())
        return
    data = await state.get_data()
    if "target_weight_kg" not in data:
        await state.clear()
        await message.answer("Данные устарели. Начните создание заново.")
        return
    target_weight_kg = Decimal(str(data["target_weight_kg"]))
    service = goal_service(db_session)
    active = await service.get_active(current_user.id)
    current = (
        active.current_weight
        if active is not None
        else await service.get_current_weight(current_user.id)
    )
    replace_existing = active is not None
    action_token = generate_action_token()
    await state.update_data(
        target_date=target_date.isoformat(),
        replace_existing=replace_existing,
        action_token=action_token,
    )
    await state.set_state(GoalCreateStates.confirm)
    await message.answer(
        goal_confirmation_text(
            target_weight_kg=target_weight_kg,
            target_date=target_date,
            start_weight_kg=current.weight_kg if current is not None else None,
            replace_existing=replace_existing,
        ),
        reply_markup=build_goal_save_keyboard(replace_existing, action_token),
    )


@router.callback_query(
    GoalCreateStates.confirm,
    ConfirmActionCallback.filter(F.action == GOAL_SAVE_ACTION),
)
async def goal_save_callback(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return
    await callback.answer()
    try:
        target_weight_kg = Decimal(str(data["target_weight_kg"]))
        target_date = (
            date.fromisoformat(str(data["target_date"]))
            if data.get("target_date")
            else None
        )
        service = goal_service(db_session)
        await service.create(
            user_id=current_user.id,
            target_weight_kg=target_weight_kg,
            target_date=target_date,
            replace_existing=bool(data.get("replace_existing")),
        )
    except (AppError, InvalidOperation, KeyError, ValueError) as error:
        text = str(error) if isinstance(error, AppError) else "Данные устарели."
        await callback.message.edit_text(text)
        await state.clear()
        return
    await show_goal(
        callback.message,
        state,
        service,
        current_user.id,
        edit=True,
    )


@router.callback_query(GoalActionCallback.filter(F.action == "complete"))
async def goal_complete_callback(
    callback: CallbackQuery,
    callback_data: GoalActionCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Завершить активную цель?",
            reply_markup=build_goal_action_confirmation_keyboard(
                callback_data.goal_id,
                "complete",
            ),
        )


@router.callback_query(GoalActionCallback.filter(F.action == "cancel"))
async def goal_cancel_action_callback(
    callback: CallbackQuery,
    callback_data: GoalActionCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Отменить активную цель?",
            reply_markup=build_goal_action_confirmation_keyboard(
                callback_data.goal_id,
                "cancel",
            ),
        )


@router.callback_query(GoalActionCallback.filter(F.action == "complete_confirm"))
async def goal_complete_confirm_callback(
    callback: CallbackQuery,
    callback_data: GoalActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    service = goal_service(db_session)
    try:
        await service.complete(current_user.id, callback_data.goal_id)
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await show_goal(
        callback.message,
        state,
        service,
        current_user.id,
        edit=True,
    )


@router.callback_query(GoalActionCallback.filter(F.action == "cancel_confirm"))
async def goal_cancel_confirm_callback(
    callback: CallbackQuery,
    callback_data: GoalActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    service = goal_service(db_session)
    try:
        await service.cancel(current_user.id, callback_data.goal_id)
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await show_goal(
        callback.message,
        state,
        service,
        current_user.id,
        edit=True,
    )


@router.callback_query(F.data == GOAL_FLOW_CANCEL)
async def goal_flow_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_goal(
            callback.message,
            state,
            goal_service(db_session),
            current_user.id,
            edit=True,
        )


@router.callback_query(F.data == GOAL_BACK_MAIN)
async def goal_back_main_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")
