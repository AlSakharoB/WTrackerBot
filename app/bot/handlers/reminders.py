from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.diary import diary_service, show_day
from app.bot.keyboards.reminders import (
    REMINDER_CANCEL,
    REMINDER_TODAY,
    ReminderActionCallback,
    ReminderTypeCallback,
    ReminderWeekdayCallback,
    build_reminder_cancel_keyboard,
    build_reminders_menu_keyboard,
    build_weekdays_keyboard,
)
from app.bot.keyboards.settings import SETTINGS_REMINDERS
from app.bot.states.settings import ReminderStates
from app.db.models.reminder import ReminderSetting, ReminderType
from app.db.models.user import User
from app.exceptions import ValidationError
from app.repositories.diary import DiaryRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.weights import WeightRepository
from app.services.reminder_scheduler import ReminderScheduler
from app.services.reminders import (
    ReminderService,
    format_weekdays,
    parse_reminder_time,
    toggle_weekday,
    validate_weekdays_mask,
)
from app.utils.datetime import local_today

router = Router(name=__name__)

REMINDER_TYPE_LABELS = {
    ReminderType.WEIGH_IN: "⚖️ Взвешивание",
    ReminderType.NUTRITION: "🥗 КБЖУ",
}


def reminder_service(session: AsyncSession) -> ReminderService:
    return ReminderService(
        ReminderRepository(session),
        WeightRepository(session),
        DiaryRepository(session),
        NutritionGoalRepository(session),
    )


def reminders_text(settings: list[ReminderSetting]) -> str:
    by_type = {setting.reminder_type: setting for setting in settings}
    lines = ["🔔 <b>Напоминания</b>", ""]
    for reminder_type in ReminderType:
        setting = by_type.get(reminder_type)
        label = REMINDER_TYPE_LABELS[reminder_type]
        if setting is None or not setting.enabled:
            lines.append(f"{label}: выключено")
        else:
            lines.append(
                f"{label}: {format_weekdays(setting.weekdays_mask)} · "
                f"{setting.time_local:%H:%M}"
            )
    lines.extend(["", "Время указано в вашем часовом поясе."])
    return "\n".join(lines)


async def show_reminders_menu(
    message: Message,
    state: FSMContext,
    service: ReminderService,
    user_id: int,
    *,
    edit: bool,
) -> None:
    settings = await service.list_for_user(user_id)
    await state.clear()
    text = reminders_text(settings)
    markup = build_reminders_menu_keyboard(settings)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == SETTINGS_REMINDERS)
@router.callback_query(F.data == REMINDER_CANCEL)
async def reminders_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_reminders_menu(
            callback.message,
            state,
            reminder_service(db_session),
            current_user.id,
            edit=True,
        )


@router.callback_query(ReminderTypeCallback.filter())
async def reminder_type_callback(
    callback: CallbackQuery,
    callback_data: ReminderTypeCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    settings = await reminder_service(db_session).list_for_user(current_user.id)
    current = next(
        (
            setting
            for setting in settings
            if setting.reminder_type is callback_data.reminder_type
        ),
        None,
    )
    weekdays_mask = current.weekdays_mask if current is not None else 0
    await state.clear()
    await state.update_data(
        reminder_type=callback_data.reminder_type.value,
        weekdays_mask=weekdays_mask,
    )
    await state.set_state(ReminderStates.choose_weekdays)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"{REMINDER_TYPE_LABELS[callback_data.reminder_type]}\n\n"
            "Выберите дни недели:",
            reply_markup=build_weekdays_keyboard(
                callback_data.reminder_type,
                weekdays_mask,
            ),
        )


@router.callback_query(
    ReminderStates.choose_weekdays,
    ReminderWeekdayCallback.filter(),
)
async def reminder_weekday_callback(
    callback: CallbackQuery,
    callback_data: ReminderWeekdayCallback,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    if data.get("reminder_type") != callback_data.reminder_type.value:
        await callback.answer("Настройка устарела. Начните заново.", show_alert=True)
        await state.clear()
        return
    try:
        weekdays_mask = toggle_weekday(
            int(data.get("weekdays_mask", 0)),
            callback_data.weekday,
        )
    except (ValidationError, TypeError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.update_data(weekdays_mask=weekdays_mask)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=build_weekdays_keyboard(
                callback_data.reminder_type,
                weekdays_mask,
            )
        )


@router.callback_query(
    ReminderStates.choose_weekdays,
    ReminderActionCallback.filter(F.action == "choose_time"),
)
async def reminder_choose_time_callback(
    callback: CallbackQuery,
    callback_data: ReminderActionCallback,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    try:
        if data.get("reminder_type") != callback_data.reminder_type.value:
            raise ValidationError("Настройка устарела. Начните заново.")
        validate_weekdays_mask(int(data.get("weekdays_mask", 0)))
    except (ValidationError, TypeError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.set_state(ReminderStates.wait_time)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите локальное время в формате Ч:ММ.\nНапример: 8:00",
            reply_markup=build_reminder_cancel_keyboard(),
        )


@router.message(ReminderStates.wait_time)
async def reminder_time_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    reminder_scheduler: ReminderScheduler,
) -> None:
    try:
        time_local = parse_reminder_time(message.text or "")
        data = await state.get_data()
        reminder_type = ReminderType(str(data["reminder_type"]))
        weekdays_mask = int(data["weekdays_mask"])
        setting = await reminder_service(db_session).configure(
            user_id=current_user.id,
            reminder_type=reminder_type,
            time_local=time_local,
            weekdays_mask=weekdays_mask,
        )
    except ValidationError as error:
        await message.answer(
            str(error),
            reply_markup=build_reminder_cancel_keyboard(),
        )
        return
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await message.answer("Данные устарели. Настройте напоминание заново.")
        return
    reminder_scheduler.schedule(setting, current_user.timezone)
    await show_reminders_menu(
        message,
        state,
        reminder_service(db_session),
        current_user.id,
        edit=False,
    )


@router.callback_query(
    ReminderActionCallback.filter(F.action.in_({"disable_menu", "disable_notice"}))
)
async def reminder_disable_callback(
    callback: CallbackQuery,
    callback_data: ReminderActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    reminder_scheduler: ReminderScheduler,
) -> None:
    await reminder_service(db_session).disable(
        current_user.id,
        callback_data.reminder_type,
    )
    reminder_scheduler.remove(current_user.id, callback_data.reminder_type)
    await callback.answer("Напоминание отключено")
    if callback.message is None:
        return
    if callback_data.action == "disable_notice":
        await state.clear()
        await callback.message.edit_text("🔕 Напоминание отключено.")
    else:
        await show_reminders_menu(
            callback.message,
            state,
            reminder_service(db_session),
            current_user.id,
            edit=True,
        )


@router.callback_query(F.data == REMINDER_TODAY)
async def reminder_today_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_day(
            callback.message,
            state,
            diary_service(db_session),
            current_user.id,
            local_today(current_user.timezone),
            edit=True,
        )
