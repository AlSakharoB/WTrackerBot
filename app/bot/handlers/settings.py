from datetime import timedelta
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.handlers.common import HELP_TEXT
from app.bot.keyboards.actions import (
    NUTRITION_GOAL_TODAY_ACTION,
    NUTRITION_GOAL_TOMORROW_ACTION,
    ConfirmActionCallback,
)
from app.bot.keyboards.main import SETTINGS_BUTTON, build_main_menu_keyboard
from app.bot.keyboards.settings import (
    NUTRITION_GOAL_CANCEL,
    NUTRITION_GOAL_CREATE,
    SETTINGS_ABOUT,
    SETTINGS_BACK_MAIN,
    SETTINGS_DELETE,
    SETTINGS_DELETE_CONTINUE,
    SETTINGS_DIARY,
    SETTINGS_DISPLAY,
    SETTINGS_HELP,
    SETTINGS_MENU,
    SETTINGS_MY_DATA,
    SETTINGS_NUTRITION_GOALS,
    SETTINGS_PRIVACY,
    SETTINGS_TIMEZONE,
    AfterFoodAddCallback,
    NumberFormatCallback,
    NutritionGoalActionCallback,
    NutritionGoalSkipCallback,
    TimezoneCallback,
    build_about_keyboard,
    build_delete_phrase_keyboard,
    build_delete_warning_keyboard,
    build_diary_behavior_keyboard,
    build_my_data_keyboard,
    build_number_format_keyboard,
    build_nutrition_goal_date_keyboard,
    build_nutrition_goal_disable_keyboard,
    build_nutrition_goal_input_keyboard,
    build_nutrition_goal_menu_keyboard,
    build_privacy_keyboard,
    build_settings_help_keyboard,
    build_settings_menu_keyboard,
    build_timezone_keyboard,
)
from app.bot.states.settings import NutritionGoalStates, SettingsDeleteStates
from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.user import User
from app.exceptions import ValidationError
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.privacy import PrivacyRepository
from app.repositories.users import UserRepository
from app.services.action_lock import generate_action_token
from app.services.nutrition_goals import (
    NutritionGoalData,
    NutritionGoalService,
    parse_nutrition_target,
    validate_nutrition_goal,
)
from app.services.privacy import PrivacyService, UserDataSummary
from app.services.reminder_scheduler import ReminderScheduler
from app.services.settings import UserSettingsService
from app.user_settings import AfterFoodAddAction, NumberFormat
from app.utils.datetime import local_today
from app.utils.decimal import format_decimal
from app.utils.formatting import format_date

router = Router(name=__name__)


def settings_service(session: AsyncSession) -> UserSettingsService:
    return UserSettingsService(UserRepository(session))


def privacy_service(
    session: AsyncSession,
    default_timezone: str,
) -> PrivacyService:
    return PrivacyService(
        PrivacyRepository(session),
        default_timezone=default_timezone,
    )


def nutrition_goal_service(session: AsyncSession) -> NutritionGoalService:
    return NutritionGoalService(NutritionGoalRepository(session))


def settings_menu_text() -> str:
    return """⚙️ <b>Настройки</b>

Выберите раздел:"""


def number_format_text(current: NumberFormat) -> str:
    labels = {
        NumberFormat.AUTOMATIC: "Автоматически",
        NumberFormat.ONE_DECIMAL: "1 знак",
        NumberFormat.TWO_DECIMALS: "2 знака",
    }
    return f"""🎛 <b>Отображение</b>

🔢 Точность чисел
Текущая: {labels[current]}"""


def diary_behavior_text(current: AfterFoodAddAction) -> str:
    labels = {
        AfterFoodAddAction.OPEN_TODAY: "Открыть «Сегодня»",
        AfterFoodAddAction.STAY: "Остаться в текущем разделе",
    }
    return f"""📅 <b>Поведение дневника</b>

После добавления еды:
{labels[current]}"""


def nutrition_goal_text(goal: NutritionGoal | None) -> str:
    if goal is None:
        return "🎯 <b>Цели КБЖУ</b>\n\nЦели пока не настроены."
    values = (
        ("🔥 Калории", goal.kcal_target, "ккал"),
        ("🥩 Белки", goal.protein_target_g, "г"),
        ("🥑 Жиры", goal.fat_target_g, "г"),
        ("🍞 Углеводы", goal.carbs_target_g, "г"),
    )
    lines = ["🎯 <b>Цели КБЖУ</b>", ""]
    lines.extend(
        f"{label}: {format_decimal(value)} {unit}"
        for label, value, unit in values
        if value is not None
    )
    lines.extend(["", f"Действуют с: {format_date(goal.effective_from)}"])
    return "\n".join(lines)


NUTRITION_GOAL_FIELDS = (
    ("kcal_target", NutritionGoalStates.wait_kcal, "Введите цель по калориям:"),
    (
        "protein_target_g",
        NutritionGoalStates.wait_protein,
        "Введите цель по белкам в граммах:",
    ),
    (
        "fat_target_g",
        NutritionGoalStates.wait_fat,
        "Введите цель по жирам в граммах:",
    ),
    (
        "carbs_target_g",
        NutritionGoalStates.wait_carbs,
        "Введите цель по углеводам в граммах:",
    ),
)
NUTRITION_GOAL_STATE_FIELDS = {
    state.state: field for field, state, _prompt in NUTRITION_GOAL_FIELDS
}


def nutrition_goal_data(data: dict[str, object]) -> NutritionGoalData:
    def optional_decimal(field: str) -> Decimal | None:
        value = data.get(field)
        return Decimal(str(value)) if value is not None else None

    return NutritionGoalData(
        kcal_target=optional_decimal("kcal_target"),
        protein_target_g=optional_decimal("protein_target_g"),
        fat_target_g=optional_decimal("fat_target_g"),
        carbs_target_g=optional_decimal("carbs_target_g"),
    )


def user_data_text(summary: UserDataSummary) -> str:
    return f"""📊 <b>Мои данные</b>

Ингредиентов: {summary.ingredients}
Блюд: {summary.dishes}
Записей питания: {summary.diary_entries}
Записей веса: {summary.weight_entries}
Активных целей: {summary.active_goals}"""


DELETE_WARNING_TEXT = """🗑 <b>Удалить все мои данные</b>

Вы уверены?

Будут удалены:
• ингредиенты;
• блюда;
• дневник питания;
• вес;
• цели;
• пользовательские настройки.

Это действие нельзя отменить."""

DELETE_PHRASE_TEXT = """Для подтверждения отправьте:

<b>УДАЛИТЬ</b>"""


def app_version() -> str:
    try:
        return version("nutrition-bot")
    except PackageNotFoundError:
        return "0.1.0"


async def edit_callback(
    callback: CallbackQuery,
    text: str,
    reply_markup: object,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=reply_markup)


@router.message(F.text == SETTINGS_BUTTON)
async def settings_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        settings_menu_text(),
        reply_markup=build_settings_menu_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_MENU)
async def settings_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_callback(callback, settings_menu_text(), build_settings_menu_keyboard())


@router.callback_query(F.data == SETTINGS_TIMEZONE)
async def timezone_screen(callback: CallbackQuery, current_user: User) -> None:
    await edit_callback(
        callback,
        f"🕒 <b>Часовой пояс</b>\n\nТекущий:\n{current_user.timezone}",
        build_timezone_keyboard(current_user.timezone),
    )


@router.callback_query(TimezoneCallback.filter())
async def timezone_change(
    callback: CallbackQuery,
    callback_data: TimezoneCallback,
    current_user: User,
    db_session: AsyncSession,
    reminder_scheduler: ReminderScheduler | None = None,
) -> None:
    user = await settings_service(db_session).set_timezone(
        current_user.id,
        callback_data.timezone,
    )
    if reminder_scheduler is not None:
        await reminder_scheduler.reschedule_user_timezone(user.id, user.timezone)
    await edit_callback(
        callback,
        f"🕒 <b>Часовой пояс</b>\n\nТекущий:\n{user.timezone}",
        build_timezone_keyboard(user.timezone),
    )


@router.callback_query(F.data == SETTINGS_DISPLAY)
async def display_screen(callback: CallbackQuery, current_user: User) -> None:
    current = NumberFormat(current_user.number_format)
    await edit_callback(
        callback,
        number_format_text(current),
        build_number_format_keyboard(current),
    )


@router.callback_query(NumberFormatCallback.filter())
async def number_format_change(
    callback: CallbackQuery,
    callback_data: NumberFormatCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    user = await settings_service(db_session).set_number_format(
        current_user.id,
        callback_data.value,
    )
    current = NumberFormat(user.number_format)
    await edit_callback(
        callback,
        number_format_text(current),
        build_number_format_keyboard(current),
    )


@router.callback_query(F.data == SETTINGS_DIARY)
async def diary_behavior_screen(callback: CallbackQuery, current_user: User) -> None:
    current = AfterFoodAddAction(current_user.after_food_add_action)
    await edit_callback(
        callback,
        diary_behavior_text(current),
        build_diary_behavior_keyboard(current),
    )


@router.callback_query(AfterFoodAddCallback.filter())
async def diary_behavior_change(
    callback: CallbackQuery,
    callback_data: AfterFoodAddCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    user = await settings_service(db_session).set_after_food_add_action(
        current_user.id,
        callback_data.value,
    )
    current = AfterFoodAddAction(user.after_food_add_action)
    await edit_callback(
        callback,
        diary_behavior_text(current),
        build_diary_behavior_keyboard(current),
    )


async def show_nutrition_goal_screen(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    goal = await nutrition_goal_service(db_session).get_open(current_user.id)
    await state.clear()
    await edit_callback(
        callback,
        nutrition_goal_text(goal),
        build_nutrition_goal_menu_keyboard(goal.id if goal is not None else None),
    )


async def advance_nutrition_goal_flow(
    message: Message,
    state: FSMContext,
    current_field: str,
    *,
    edit: bool,
) -> None:
    current_index = next(
        index
        for index, (field, _state, _prompt) in enumerate(NUTRITION_GOAL_FIELDS)
        if field == current_field
    )
    if current_index + 1 < len(NUTRITION_GOAL_FIELDS):
        field, next_state, prompt = NUTRITION_GOAL_FIELDS[current_index + 1]
        await state.set_state(next_state)
        markup = build_nutrition_goal_input_keyboard(field)
        if edit:
            await message.edit_text(prompt, reply_markup=markup)
        else:
            await message.answer(prompt, reply_markup=markup)
        return

    try:
        validate_nutrition_goal(nutrition_goal_data(await state.get_data()))
    except ValidationError as error:
        field, first_state, prompt = NUTRITION_GOAL_FIELDS[0]
        await state.set_state(first_state)
        text = f"{error}\n\n{prompt}"
        markup = build_nutrition_goal_input_keyboard(field)
        if edit:
            await message.edit_text(text, reply_markup=markup)
        else:
            await message.answer(text, reply_markup=markup)
        return

    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(NutritionGoalStates.choose_date)
    text = "С какого дня применять новые цели?"
    markup = build_nutrition_goal_date_keyboard(action_token)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == SETTINGS_NUTRITION_GOALS)
async def nutrition_goals_screen(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await show_nutrition_goal_screen(callback, state, current_user, db_session)


@router.callback_query(F.data == NUTRITION_GOAL_CREATE)
async def nutrition_goal_create(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    field, first_state, prompt = NUTRITION_GOAL_FIELDS[0]
    await state.set_state(first_state)
    if callback.message is not None:
        await callback.message.edit_text(
            prompt,
            reply_markup=build_nutrition_goal_input_keyboard(field),
        )


@router.message(NutritionGoalStates.wait_kcal)
@router.message(NutritionGoalStates.wait_protein)
@router.message(NutritionGoalStates.wait_fat)
@router.message(NutritionGoalStates.wait_carbs)
async def nutrition_goal_value_message(
    message: Message,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()
    field = NUTRITION_GOAL_STATE_FIELDS.get(current_state)
    if field is None:
        await state.clear()
        await message.answer("Данные устарели. Откройте настройки заново.")
        return
    try:
        value = parse_nutrition_target(field, message.text or "")
    except ValidationError as error:
        await message.answer(
            str(error),
            reply_markup=build_nutrition_goal_input_keyboard(field),
        )
        return
    await state.update_data(**{field: str(value)})
    await advance_nutrition_goal_flow(message, state, field, edit=False)


@router.callback_query(NutritionGoalSkipCallback.filter())
async def nutrition_goal_skip(
    callback: CallbackQuery,
    callback_data: NutritionGoalSkipCallback,
    state: FSMContext,
) -> None:
    current_state = await state.get_state()
    expected_field = NUTRITION_GOAL_STATE_FIELDS.get(current_state)
    if expected_field != callback_data.field:
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(**{expected_field: None})
    if callback.message is not None:
        await advance_nutrition_goal_flow(
            callback.message,
            state,
            expected_field,
            edit=True,
        )


@router.callback_query(
    NutritionGoalStates.choose_date,
    ConfirmActionCallback.filter(F.action == NUTRITION_GOAL_TODAY_ACTION),
)
@router.callback_query(
    NutritionGoalStates.choose_date,
    ConfirmActionCallback.filter(F.action == NUTRITION_GOAL_TOMORROW_ACTION),
)
async def nutrition_goal_effective_date(
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
    today = local_today(current_user.timezone)
    effective_from = (
        today
        if callback_data.action == NUTRITION_GOAL_TODAY_ACTION
        else today + timedelta(days=1)
    )
    goal = await nutrition_goal_service(db_session).set_goal(
        current_user.id,
        nutrition_goal_data(data),
        effective_from,
    )
    await callback.answer("Цели сохранены")
    await state.clear()
    await callback.message.edit_text(
        nutrition_goal_text(goal),
        reply_markup=build_nutrition_goal_menu_keyboard(goal.id),
    )


@router.callback_query(NutritionGoalActionCallback.filter(F.action == "disable"))
async def nutrition_goal_disable(
    callback: CallbackQuery,
    callback_data: NutritionGoalActionCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Отключить цели КБЖУ с сегодняшнего дня?",
            reply_markup=build_nutrition_goal_disable_keyboard(callback_data.goal_id),
        )


@router.callback_query(
    NutritionGoalActionCallback.filter(F.action == "disable_confirm")
)
async def nutrition_goal_disable_confirm(
    callback: CallbackQuery,
    callback_data: NutritionGoalActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await nutrition_goal_service(db_session).disable(
        current_user.id,
        callback_data.goal_id,
        local_today(current_user.timezone),
    )
    await callback.answer("Цели отключены")
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            nutrition_goal_text(None),
            reply_markup=build_nutrition_goal_menu_keyboard(None),
        )


@router.callback_query(F.data == NUTRITION_GOAL_CANCEL)
async def nutrition_goal_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await show_nutrition_goal_screen(callback, state, current_user, db_session)


@router.callback_query(F.data == SETTINGS_ABOUT)
async def about_screen(callback: CallbackQuery, app_environment: str) -> None:
    await edit_callback(
        callback,
        f"ℹ️ <b>О боте</b>\n\nВерсия: {app_version()}\nСреда: {app_environment}",
        build_about_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_HELP)
async def settings_help_screen(callback: CallbackQuery) -> None:
    await edit_callback(callback, HELP_TEXT, build_settings_help_keyboard())


@router.callback_query(F.data == SETTINGS_PRIVACY)
async def privacy_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_callback(
        callback,
        "🔐 <b>Данные и приватность</b>",
        build_privacy_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_MY_DATA)
async def my_data_screen(
    callback: CallbackQuery,
    current_user: User,
    db_session: AsyncSession,
    default_timezone: str,
) -> None:
    summary = await privacy_service(db_session, default_timezone).summary(
        current_user.id
    )
    await edit_callback(callback, user_data_text(summary), build_my_data_keyboard())


@router.callback_query(F.data == SETTINGS_DELETE)
async def delete_warning_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await edit_callback(
        callback,
        DELETE_WARNING_TEXT,
        build_delete_warning_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_DELETE_CONTINUE)
async def delete_phrase_screen(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsDeleteStates.wait_phrase)
    await edit_callback(
        callback,
        DELETE_PHRASE_TEXT,
        build_delete_phrase_keyboard(),
    )


@router.message(SettingsDeleteStates.wait_phrase)
async def delete_phrase_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
    default_timezone: str,
    reminder_scheduler: ReminderScheduler | None = None,
) -> None:
    if message.text != "УДАЛИТЬ":
        await state.clear()
        await message.answer(
            "Удаление отменено.",
            reply_markup=build_main_menu_keyboard(),
        )
        return
    await privacy_service(db_session, default_timezone).clear_user_data(current_user.id)
    if reminder_scheduler is not None:
        reminder_scheduler.remove_user(current_user.id)
    await state.clear()
    await message.answer(
        "Все ваши данные удалены. Бот готов к дальнейшей работе.",
        reply_markup=build_main_menu_keyboard(),
    )


@router.callback_query(F.data == SETTINGS_BACK_MAIN)
async def settings_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")
        await callback.message.answer(
            "Выберите раздел:",
            reply_markup=build_main_menu_keyboard(),
        )
