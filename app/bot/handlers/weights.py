from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import WEIGHT_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.main import WEIGHT_BUTTON
from app.bot.keyboards.weights import (
    WEIGHT_ADD,
    WEIGHT_BACK_MAIN,
    WEIGHT_CANCEL,
    WEIGHT_HISTORY,
    WEIGHT_MENU,
    WEIGHT_NOOP,
    WeightEntryCallback,
    WeightPageCallback,
    WeightTimeCallback,
    build_time_choice_keyboard,
    build_weight_cancel_keyboard,
    build_weight_delete_keyboard,
    build_weight_entry_keyboard,
    build_weight_history_keyboard,
    build_weight_menu_keyboard,
    build_weight_save_keyboard,
)
from app.bot.states.weights import WeightAddStates, WeightEditStates
from app.db.models.user import User
from app.db.models.weight import WeightEntry
from app.exceptions import AppError, ValidationError
from app.repositories.weights import WeightRepository
from app.services.action_lock import generate_action_token
from app.services.weights import (
    WeightService,
    WeightSummary,
    now_in_timezone,
    parse_measured_at,
    parse_weight,
    today_morning,
)
from app.utils.decimal import format_decimal
from app.utils.formatting import format_datetime, format_signed_decimal

router = Router(name=__name__)


def weight_service(session: AsyncSession) -> WeightService:
    return WeightService(WeightRepository(session))


def weight_entry_text(entry: WeightEntry, timezone_name: str) -> str:
    return f"""⚖️ <b>{format_decimal(entry.weight_kg)} кг</b>

🕒 {format_datetime(entry.measured_at, timezone_name)}"""


def weight_summary_text(summary: WeightSummary, timezone_name: str) -> str:
    if summary.current is None or summary.first is None:
        return "⚖️ <b>Вес</b>\n\nУ вас пока нет измерений."

    difference = summary.difference_kg or Decimal("0")
    difference_text = format_signed_decimal(difference)
    lines = [
        "⚖️ <b>Вес</b>",
        "",
        f"Текущий: <b>{format_decimal(summary.current.weight_kg)} кг</b>",
        f"Первый: {format_decimal(summary.first.weight_kg)} кг",
        f"Изменение: {difference_text} кг",
        "",
        "Последние записи:",
    ]
    for entry in summary.recent:
        measured_at = format_datetime(entry.measured_at, timezone_name).split()[0]
        lines.append(f"{measured_at} — {format_decimal(entry.weight_kg)} кг")
    return "\n".join(lines)


def weight_confirmation_text(weight_kg: Decimal, measured_at: datetime) -> str:
    return f"""⚖️ Вес: <b>{format_decimal(weight_kg)} кг</b>
🕒 {measured_at:%d.%m.%Y %H:%M}

Сохранить?"""


async def show_weight_menu(
    message: Message,
    state: FSMContext,
    service: WeightService,
    user: User,
    *,
    edit: bool,
) -> None:
    summary = await service.get_summary(user.id)
    await state.clear()
    text = weight_summary_text(summary, user.timezone)
    markup = build_weight_menu_keyboard(summary.current is not None)
    if edit and message.photo:
        await message.delete()
        await message.answer(text, reply_markup=markup)
    elif edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def show_weight_history(
    message: Message,
    service: WeightService,
    user: User,
    page_number: int,
) -> None:
    page = await service.list_page(user.id, page_number)
    if page.total == 0:
        text = "История измерений пока пуста."
    else:
        lines = [f"📋 <b>История веса — {page.page}/{page.pages}</b>", ""]
        for entry in page.items:
            lines.append(
                f"{format_datetime(entry.measured_at, user.timezone)} — "
                f"{format_decimal(entry.weight_kg)} кг"
            )
        text = "\n".join(lines)
    await message.edit_text(
        text,
        reply_markup=build_weight_history_keyboard(page, user.timezone),
    )


async def prepare_confirmation(
    message: Message,
    state: FSMContext,
    measured_at: datetime,
) -> None:
    data = await state.get_data()
    if "weight_kg" not in data:
        await state.clear()
        await message.edit_text("Данные устарели. Начните добавление заново.")
        return
    weight_kg = Decimal(str(data["weight_kg"]))
    action_token = generate_action_token()
    await state.update_data(
        measured_at=measured_at.isoformat(),
        action_token=action_token,
    )
    await state.set_state(WeightAddStates.confirm)
    await message.edit_text(
        weight_confirmation_text(weight_kg, measured_at),
        reply_markup=build_weight_save_keyboard(action_token),
    )


@router.message(Command("weight"))
@router.message(F.text == WEIGHT_BUTTON)
async def weight_menu_handler(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await show_weight_menu(
        message,
        state,
        weight_service(db_session),
        current_user,
        edit=False,
    )


@router.callback_query(F.data == WEIGHT_MENU)
async def weight_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_weight_menu(
            callback.message,
            state,
            weight_service(db_session),
            current_user,
            edit=True,
        )


@router.callback_query(F.data == WEIGHT_NOOP)
async def weight_noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == WEIGHT_ADD)
async def weight_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(WeightAddStates.wait_weight)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите вес в килограммах:",
            reply_markup=build_weight_cancel_keyboard(),
        )


@router.message(WeightAddStates.wait_weight)
async def weight_add_value_message(message: Message, state: FSMContext) -> None:
    try:
        weight_kg = parse_weight(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_weight_cancel_keyboard())
        return
    await state.update_data(weight_kg=str(weight_kg))
    await state.set_state(WeightAddStates.choose_time)
    await message.answer(
        "Когда измерен вес?",
        reply_markup=build_time_choice_keyboard(),
    )


@router.callback_query(WeightTimeCallback.filter())
async def weight_time_callback(
    callback: CallbackQuery,
    callback_data: WeightTimeCallback,
    state: FSMContext,
    current_user: User,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if callback_data.action == "custom":
        await state.set_state(WeightAddStates.wait_datetime)
        await callback.message.edit_text(
            "Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ:",
            reply_markup=build_weight_cancel_keyboard(),
        )
        return
    measured_at = (
        now_in_timezone(current_user.timezone)
        if callback_data.action == "now"
        else today_morning(current_user.timezone)
    )
    await prepare_confirmation(callback.message, state, measured_at)


@router.message(WeightAddStates.wait_datetime)
async def weight_datetime_message(
    message: Message,
    state: FSMContext,
    current_user: User,
) -> None:
    try:
        measured_at = parse_measured_at(
            message.text or "",
            current_user.timezone,
        )
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_weight_cancel_keyboard())
        return
    data = await state.get_data()
    if "weight_kg" not in data:
        await state.clear()
        await message.answer("Данные устарели. Начните добавление заново.")
        return
    weight_kg = Decimal(str(data["weight_kg"]))
    action_token = generate_action_token()
    await state.update_data(
        measured_at=measured_at.isoformat(),
        action_token=action_token,
    )
    await state.set_state(WeightAddStates.confirm)
    await message.answer(
        weight_confirmation_text(weight_kg, measured_at),
        reply_markup=build_weight_save_keyboard(action_token),
    )


@router.callback_query(
    WeightAddStates.confirm,
    ConfirmActionCallback.filter(F.action == WEIGHT_SAVE_ACTION),
)
async def weight_save_callback(
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
        weight_kg = Decimal(str(data["weight_kg"]))
        measured_at = datetime.fromisoformat(str(data["measured_at"]))
        service = weight_service(db_session)
        await service.create(
            user_id=current_user.id,
            weight_kg=weight_kg,
            measured_at=measured_at,
        )
    except (AppError, InvalidOperation, KeyError, ValueError) as error:
        text = str(error) if isinstance(error, AppError) else "Данные устарели."
        await callback.message.edit_text(text)
        await state.clear()
        return
    await show_weight_menu(
        callback.message,
        state,
        service,
        current_user,
        edit=True,
    )


@router.callback_query(F.data == WEIGHT_HISTORY)
async def weight_history_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await show_weight_history(
            callback.message,
            weight_service(db_session),
            current_user,
            1,
        )


@router.callback_query(WeightPageCallback.filter())
async def weight_page_callback(
    callback: CallbackQuery,
    callback_data: WeightPageCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_weight_history(
            callback.message,
            weight_service(db_session),
            current_user,
            callback_data.page,
        )


@router.callback_query(WeightEntryCallback.filter(F.action == "view"))
async def weight_entry_view_callback(
    callback: CallbackQuery,
    callback_data: WeightEntryCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        entry = await weight_service(db_session).get(
            current_user.id,
            callback_data.entry_id,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await callback.message.edit_text(
        weight_entry_text(entry, current_user.timezone),
        reply_markup=build_weight_entry_keyboard(entry.id, callback_data.page),
    )


@router.callback_query(WeightEntryCallback.filter(F.action == "edit_weight"))
async def weight_entry_edit_weight_callback(
    callback: CallbackQuery,
    callback_data: WeightEntryCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.update_data(
        weight_entry_id=callback_data.entry_id,
        weight_page=callback_data.page,
    )
    await state.set_state(WeightEditStates.wait_weight)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новый вес в килограммах:",
            reply_markup=build_weight_cancel_keyboard(),
        )


@router.message(WeightEditStates.wait_weight)
async def weight_entry_edit_weight_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        value = parse_weight(message.text or "")
        data = await state.get_data()
        entry = await weight_service(db_session).update_weight(
            current_user.id,
            int(data["weight_entry_id"]),
            value,
        )
        page = int(data.get("weight_page", 1))
    except (AppError, KeyError, ValueError) as error:
        text = str(error) if isinstance(error, AppError) else "Данные устарели."
        await message.answer(text, reply_markup=build_weight_cancel_keyboard())
        return
    await state.clear()
    await message.answer(
        weight_entry_text(entry, current_user.timezone),
        reply_markup=build_weight_entry_keyboard(entry.id, page),
    )


@router.callback_query(WeightEntryCallback.filter(F.action == "edit_time"))
async def weight_entry_edit_time_callback(
    callback: CallbackQuery,
    callback_data: WeightEntryCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.update_data(
        weight_entry_id=callback_data.entry_id,
        weight_page=callback_data.page,
    )
    await state.set_state(WeightEditStates.wait_datetime)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новую дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ:",
            reply_markup=build_weight_cancel_keyboard(),
        )


@router.message(WeightEditStates.wait_datetime)
async def weight_entry_edit_time_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        measured_at = parse_measured_at(
            message.text or "",
            current_user.timezone,
        )
        data = await state.get_data()
        entry = await weight_service(db_session).update_measured_at(
            current_user.id,
            int(data["weight_entry_id"]),
            measured_at,
        )
        page = int(data.get("weight_page", 1))
    except (AppError, KeyError, ValueError) as error:
        text = str(error) if isinstance(error, AppError) else "Данные устарели."
        await message.answer(text, reply_markup=build_weight_cancel_keyboard())
        return
    await state.clear()
    await message.answer(
        weight_entry_text(entry, current_user.timezone),
        reply_markup=build_weight_entry_keyboard(entry.id, page),
    )


@router.callback_query(WeightEntryCallback.filter(F.action == "delete"))
async def weight_entry_delete_callback(
    callback: CallbackQuery,
    callback_data: WeightEntryCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Удалить эту запись веса?",
            reply_markup=build_weight_delete_keyboard(
                callback_data.entry_id,
                callback_data.page,
            ),
        )


@router.callback_query(WeightEntryCallback.filter(F.action == "delete_confirm"))
async def weight_entry_delete_confirm_callback(
    callback: CallbackQuery,
    callback_data: WeightEntryCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    service = weight_service(db_session)
    try:
        await service.delete(current_user.id, callback_data.entry_id)
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await show_weight_history(
        callback.message,
        service,
        current_user,
        callback_data.page,
    )


@router.callback_query(F.data == WEIGHT_CANCEL)
async def weight_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_weight_menu(
            callback.message,
            state,
            weight_service(db_session),
            current_user,
            edit=True,
        )


@router.callback_query(F.data == WEIGHT_BACK_MAIN)
async def weight_back_main_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")
