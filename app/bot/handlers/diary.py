from datetime import date
from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import DIARY_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.diary import (
    DIARY_ADD,
    DIARY_BACK_DAY,
    DIARY_BACK_MAIN,
    DIARY_CANCEL,
    DIARY_CHOOSE_DATE,
    DIARY_EDIT,
    DIARY_NOOP,
    DiaryDateCallback,
    DiaryDishPortionCallback,
    DiaryEditPageCallback,
    DiaryEntryCallback,
    DiaryEntryMealCallback,
    DiaryMealCallback,
    DiarySourceCallback,
    DiarySourcePageCallback,
    build_add_food_keyboard,
    build_cancel_keyboard,
    build_date_choice_keyboard,
    build_day_keyboard,
    build_dish_portion_keyboard,
    build_entry_actions_keyboard,
    build_entry_delete_keyboard,
    build_entry_list_keyboard,
    build_entry_meal_keyboard,
    build_meal_keyboard,
    build_save_keyboard,
    build_source_picker_keyboard,
)
from app.bot.keyboards.main import ADD_FOOD_BUTTON, TODAY_BUTTON
from app.bot.states.diary import DiaryAddStates, DiaryDateStates, DiaryEditStates
from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.user import User
from app.exceptions import AppError, ValidationError
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.services.action_lock import generate_action_token
from app.services.diary import (
    DaySummary,
    DiaryPreview,
    DiaryService,
    parse_entry_date,
    parse_entry_grams,
)
from app.services.dishes import DishService
from app.services.ingredients import IngredientService
from app.services.nutrition import NutritionService, NutritionValues
from app.services.nutrition_goals import calculate_target_progress
from app.user_settings import AfterFoodAddAction
from app.utils.datetime import local_today
from app.utils.decimal import format_decimal
from app.utils.formatting import format_date, format_date_long
from app.utils.progress import build_progress_bar

router = Router(name=__name__)
DAY_VISIBLE_ENTRIES_LIMIT = 30

MEAL_LABELS = {
    MealType.BREAKFAST: "🌅 Завтрак",
    MealType.LUNCH: "☀️ Обед",
    MealType.DINNER: "🌙 Ужин",
    MealType.SNACK: "🍎 Перекус",
    MealType.OTHER: "🍽 Другое",
}


def diary_service(session: AsyncSession) -> DiaryService:
    return DiaryService(
        DiaryRepository(session),
        IngredientRepository(session),
        DishRepository(session),
        NutritionGoalRepository(session),
    )


def meal_name(meal_type: MealType) -> str:
    return MEAL_LABELS[meal_type].split(" ", 1)[1]


def day_text(summary: DaySummary) -> str:
    totals = summary.totals
    percentages = summary.macro_percentages
    parts = [f"📅 <b>{format_date_long(summary.entry_date)}</b>", ""]
    if summary.nutrition_goal is None:
        parts.extend(
            [
                f"🔥 <b>{format_decimal(totals.kcal)} ккал</b>",
                "",
                f"🥩 Белки: {format_decimal(totals.protein)} г",
                f"🥑 Жиры: {format_decimal(totals.fat)} г",
                f"🍞 Углеводы: {format_decimal(totals.carbs)} г",
            ]
        )
    else:
        goal = summary.nutrition_goal
        targets = (
            ("🔥 Калории", totals.kcal, goal.kcal_target, "ккал"),
            ("🥩 Белки", totals.protein, goal.protein_target_g, "г"),
            ("🥑 Жиры", totals.fat, goal.fat_target_g, "г"),
            ("🍞 Углеводы", totals.carbs, goal.carbs_target_g, "г"),
        )
        for label, consumed, target, unit in targets:
            if target is None:
                parts.append(f"{label}: {format_decimal(consumed)} {unit}")
                continue
            progress = calculate_target_progress(consumed, target)
            parts.extend(
                [
                    label,
                    f"{format_decimal(consumed)} / {format_decimal(target)} {unit}",
                    f"{build_progress_bar(progress.percentage)} "
                    f"{format_decimal(progress.percentage, 0)}%",
                ]
            )
            if progress.excess > 0:
                parts.append(f"+{format_decimal(progress.excess)} {unit}")
            parts.append("")
        if parts[-1] == "":
            parts.pop()
    parts.extend(
        [
            "",
            "Энергия из Б/Ж/У:",
            f"🥩 Б: {format_decimal(percentages.protein, 0)}%",
            f"🥑 Ж: {format_decimal(percentages.fat, 0)}%",
            f"🍞 У: {format_decimal(percentages.carbs, 0)}%",
        ]
    )
    if not summary.entries:
        parts.extend(["", "В этот день записей пока нет."])
        return "\n".join(parts)

    grouped = {meal_type: [] for meal_type in MealType}
    visible_entries = summary.entries[:DAY_VISIBLE_ENTRIES_LIMIT]
    visible_ids = {entry.id for entry in visible_entries}
    for entry in summary.entries:
        grouped[entry.meal_type].append(entry)
    for meal_type in MealType:
        entries = grouped[meal_type]
        visible_meal_entries = [entry for entry in entries if entry.id in visible_ids]
        if not visible_meal_entries:
            continue
        meal_total = NutritionService.sum_nutrition(
            NutritionValues(
                kcal=entry.kcal_snapshot,
                protein=entry.protein_snapshot,
                fat=entry.fat_snapshot,
                carbs=entry.carbs_snapshot,
            )
            for entry in entries
        )
        parts.extend(
            [
                "",
                f"{MEAL_LABELS[meal_type]} — {format_decimal(meal_total.kcal)} ккал",
            ]
        )
        parts.extend(
            f"• {escape(entry.source_name[:60])} — {format_decimal(entry.grams)} г"
            for entry in visible_meal_entries
        )
    hidden_count = len(summary.entries) - len(visible_entries)
    if hidden_count:
        parts.extend(
            [
                "",
                f"Ещё записей: {hidden_count}. Откройте «Изменить рацион».",
            ]
        )
    return "\n".join(parts)


def entry_text(entry: DiaryEntry) -> str:
    return f"""🍽 <b>{escape(entry.source_name)}</b>

{format_decimal(entry.grams)} г
🔥 {format_decimal(entry.kcal_snapshot)} ккал
🥩 Б: {format_decimal(entry.protein_snapshot)} г
🥑 Ж: {format_decimal(entry.fat_snapshot)} г
🍞 У: {format_decimal(entry.carbs_snapshot)} г

Приём пищи: {meal_name(entry.meal_type)}
Дата: {format_date(entry.entry_date)}"""


def preview_text(
    preview: DiaryPreview,
    meal_type: MealType,
    entry_date: date,
) -> str:
    nutrition = preview.nutrition
    return f"""Добавить в рацион?

🍽 <b>{escape(preview.source_name)}</b>
{format_decimal(preview.grams)} г

🔥 {format_decimal(nutrition.kcal)} ккал
🥩 Б: {format_decimal(nutrition.protein)} г
🥑 Ж: {format_decimal(nutrition.fat)} г
🍞 У: {format_decimal(nutrition.carbs)} г

Приём пищи: {meal_name(meal_type)}
Дата: {format_date(entry_date)}"""


async def show_day(
    message: Message,
    state: FSMContext,
    service: DiaryService,
    user_id: int,
    entry_date: date,
    *,
    edit: bool,
) -> None:
    summary = await service.get_day(user_id, entry_date)
    await state.clear()
    await state.update_data(view_date=entry_date.isoformat())
    if edit:
        await message.edit_text(day_text(summary), reply_markup=build_day_keyboard())
    else:
        await message.answer(day_text(summary), reply_markup=build_day_keyboard())


async def show_confirmation(
    message: Message,
    state: FSMContext,
    service: DiaryService,
    user_id: int,
) -> None:
    data = await state.get_data()
    entry_type = DiaryEntryType(str(data["entry_type"]))
    source_id = int(data["source_id"])
    grams = Decimal(str(data["grams"]))
    if entry_type is DiaryEntryType.INGREDIENT:
        preview = await service.preview_ingredient(user_id, source_id, grams)
    else:
        preview = await service.preview_dish(user_id, source_id, grams)
    meal_type = MealType(str(data["meal_type"]))
    entry_date = date.fromisoformat(str(data["entry_date"]))
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(DiaryAddStates.confirm)
    await message.edit_text(
        preview_text(preview, meal_type, entry_date),
        reply_markup=build_save_keyboard(action_token),
    )


async def finish_food_add(
    message: Message,
    state: FSMContext,
    service: DiaryService,
    user: User,
) -> None:
    action = AfterFoodAddAction(user.after_food_add_action)
    if action is AfterFoodAddAction.OPEN_TODAY:
        await show_day(
            message,
            state,
            service,
            user.id,
            local_today(user.timezone),
            edit=True,
        )
        return
    await state.clear()
    await message.edit_text(
        "✅ Еда добавлена в рацион.\n\nЧто добавить ещё?",
        reply_markup=build_add_food_keyboard(),
    )


@router.message(Command("today"))
@router.message(F.text == TODAY_BUTTON)
async def today_handler(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await show_day(
        message,
        state,
        diary_service(db_session),
        current_user.id,
        local_today(current_user.timezone),
        edit=False,
    )


@router.message(Command("addfood"))
@router.message(F.text == ADD_FOOD_BUTTON)
async def add_food_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Что добавить в рацион?",
        reply_markup=build_add_food_keyboard(),
    )


@router.callback_query(F.data == DIARY_NOOP)
async def diary_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == DIARY_ADD)
async def diary_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            "Что добавить в рацион?",
            reply_markup=build_add_food_keyboard(),
        )


@router.callback_query(DiarySourcePageCallback.filter())
async def diary_source_page_callback(
    callback: CallbackQuery,
    callback_data: DiarySourcePageCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if callback_data.entry_type is DiaryEntryType.INGREDIENT:
        page = await IngredientService(IngredientRepository(db_session)).list_page(
            current_user.id,
            callback_data.page,
        )
        empty_text = "Сначала создайте хотя бы один ингредиент."
        title = "Выберите ингредиент:"
    else:
        page = await DishService(DishRepository(db_session)).list_page(
            current_user.id,
            callback_data.page,
        )
        empty_text = "Сначала создайте хотя бы одно блюдо."
        title = "Выберите блюдо:"
    text = title if page.total else empty_text
    await callback.message.edit_text(
        text,
        reply_markup=build_source_picker_keyboard(page, callback_data.entry_type),
    )


@router.callback_query(DiarySourceCallback.filter())
async def diary_source_callback(
    callback: CallbackQuery,
    callback_data: DiarySourceCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await state.clear()
    await state.update_data(
        entry_type=callback_data.entry_type.value,
        source_id=callback_data.source_id,
    )
    if callback_data.entry_type is DiaryEntryType.INGREDIENT:
        try:
            ingredient = await IngredientService(IngredientRepository(db_session)).get(
                current_user.id, callback_data.source_id
            )
        except AppError as error:
            await callback.message.edit_text(str(error))
            return
        await state.set_state(DiaryAddStates.wait_grams)
        await callback.message.edit_text(
            f"🥕 <b>{escape(ingredient.name)}</b>\n\nВведите количество в граммах:",
            reply_markup=build_cancel_keyboard(),
        )
        return

    try:
        details = await DishService(DishRepository(db_session)).get(
            current_user.id,
            callback_data.source_id,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await state.update_data(total_weight=str(details.nutrition.total_weight))
    await callback.message.edit_text(
        f"🍲 <b>{escape(details.dish.name)}</b>\n\nЧто добавить?",
        reply_markup=build_dish_portion_keyboard(
            details.dish.id,
            format_decimal(details.nutrition.total_weight),
        ),
    )


@router.callback_query(DiaryDishPortionCallback.filter())
async def diary_dish_portion_callback(
    callback: CallbackQuery,
    callback_data: DiaryDishPortionCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    if int(data.get("source_id", 0)) != callback_data.dish_id:
        await callback.message.edit_text("Выбор устарел. Начните добавление заново.")
        await state.clear()
        return
    if callback_data.mode == "custom":
        await state.set_state(DiaryAddStates.wait_grams)
        await callback.message.edit_text(
            "Введите количество блюда в граммах:",
            reply_markup=build_cancel_keyboard(),
        )
        return
    await state.update_data(grams=str(data["total_weight"]))
    await state.set_state(DiaryAddStates.choose_meal)
    await callback.message.edit_text(
        "Выберите приём пищи:",
        reply_markup=build_meal_keyboard(),
    )


@router.message(DiaryAddStates.wait_grams)
async def diary_grams_message(message: Message, state: FSMContext) -> None:
    try:
        grams = parse_entry_grams(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await state.update_data(grams=str(grams))
    await state.set_state(DiaryAddStates.choose_meal)
    await message.answer("Выберите приём пищи:", reply_markup=build_meal_keyboard())


@router.callback_query(DiaryMealCallback.filter())
async def diary_meal_callback(
    callback: CallbackQuery,
    callback_data: DiaryMealCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    data = await state.get_data()
    if "source_id" not in data or "grams" not in data:
        await callback.message.edit_text("Выбор устарел. Начните добавление заново.")
        await state.clear()
        return
    await state.update_data(meal_type=callback_data.meal_type.value)
    await state.set_state(DiaryAddStates.choose_date)
    await callback.message.edit_text(
        "Выберите дату:",
        reply_markup=build_date_choice_keyboard(),
    )


@router.callback_query(DiaryDateCallback.filter())
async def diary_date_callback(
    callback: CallbackQuery,
    callback_data: DiaryDateCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    if callback_data.action == "custom":
        await state.set_state(DiaryAddStates.wait_date)
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=build_cancel_keyboard(),
        )
        return
    await state.update_data(entry_date=local_today(current_user.timezone).isoformat())
    try:
        await show_confirmation(
            callback.message,
            state,
            diary_service(db_session),
            current_user.id,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        await state.clear()


@router.message(DiaryAddStates.wait_date)
async def diary_add_date_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        entry_date = parse_entry_date(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await state.update_data(entry_date=entry_date.isoformat())
    try:
        data = await state.get_data()
        entry_type = DiaryEntryType(str(data["entry_type"]))
        source_id = int(data["source_id"])
        grams = Decimal(str(data["grams"]))
        service = diary_service(db_session)
        preview = (
            await service.preview_ingredient(current_user.id, source_id, grams)
            if entry_type is DiaryEntryType.INGREDIENT
            else await service.preview_dish(current_user.id, source_id, grams)
        )
        meal_type = MealType(str(data["meal_type"]))
    except AppError as error:
        await message.answer(str(error))
        await state.clear()
        return
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(DiaryAddStates.confirm)
    await message.answer(
        preview_text(preview, meal_type, entry_date),
        reply_markup=build_save_keyboard(action_token),
    )


@router.callback_query(
    DiaryAddStates.confirm,
    ConfirmActionCallback.filter(F.action == DIARY_SAVE_ACTION),
)
async def diary_save_callback(
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
        entry_type = DiaryEntryType(str(data["entry_type"]))
        source_id = int(data["source_id"])
        grams = Decimal(str(data["grams"]))
        meal_type = MealType(str(data["meal_type"]))
        entry_date = date.fromisoformat(str(data["entry_date"]))
        service = diary_service(db_session)
        if entry_type is DiaryEntryType.INGREDIENT:
            await service.add_ingredient(
                user_id=current_user.id,
                ingredient_id=source_id,
                grams=grams,
                meal_type=meal_type,
                entry_date=entry_date,
            )
        else:
            await service.add_dish(
                user_id=current_user.id,
                dish_id=source_id,
                grams=grams,
                meal_type=meal_type,
                entry_date=entry_date,
            )
    except (AppError, KeyError, ValueError) as error:
        await callback.message.edit_text(
            str(error) if isinstance(error, AppError) else "Данные устарели."
        )
        await state.clear()
        return
    await finish_food_add(callback.message, state, service, current_user)


@router.callback_query(F.data == DIARY_CHOOSE_DATE)
async def choose_diary_date_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(DiaryDateStates.wait_date)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите дату в формате ДД.ММ.ГГГГ:",
            reply_markup=build_cancel_keyboard(),
        )


@router.message(DiaryDateStates.wait_date)
async def choose_diary_date_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        entry_date = parse_entry_date(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await show_day(
        message,
        state,
        diary_service(db_session),
        current_user.id,
        entry_date,
        edit=False,
    )


async def current_view_date(state: FSMContext, user: User) -> date:
    data = await state.get_data()
    raw_value = data.get("view_date")
    return (
        date.fromisoformat(str(raw_value)) if raw_value else local_today(user.timezone)
    )


async def show_diary_edit_page(
    message: Message,
    state: FSMContext,
    service: DiaryService,
    user: User,
    page_number: int,
) -> None:
    entry_date = await current_view_date(state, user)
    page = await service.list_page(user.id, entry_date, page_number)
    await state.update_data(
        view_date=entry_date.isoformat(),
        edit_page=page.page,
    )
    text = (
        f"Выберите запись для изменения — {page.page}/{page.pages}:"
        if page.total
        else "В этот день записей нет."
    )
    await message.edit_text(text, reply_markup=build_entry_list_keyboard(page))


@router.callback_query(F.data == DIARY_BACK_DAY)
async def diary_back_day_callback(
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
            await current_view_date(state, current_user),
            edit=True,
        )


@router.callback_query(F.data == DIARY_EDIT)
async def diary_edit_callback(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    await show_diary_edit_page(
        callback.message,
        state,
        diary_service(db_session),
        current_user,
        1,
    )


@router.callback_query(DiaryEditPageCallback.filter())
async def diary_edit_page_callback(
    callback: CallbackQuery,
    callback_data: DiaryEditPageCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_diary_edit_page(
            callback.message,
            state,
            diary_service(db_session),
            current_user,
            callback_data.page,
        )


@router.callback_query(DiaryEntryCallback.filter(F.action == "view"))
async def diary_entry_view_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        entry = await diary_service(db_session).get(
            current_user.id,
            callback_data.entry_id,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await callback.message.edit_text(
        entry_text(entry),
        reply_markup=build_entry_actions_keyboard(entry.id, callback_data.page),
    )


@router.callback_query(DiaryEntryCallback.filter(F.action == "grams"))
async def diary_entry_grams_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.update_data(
        edit_entry_id=callback_data.entry_id,
        edit_page=callback_data.page,
    )
    await state.set_state(DiaryEditStates.wait_grams)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новое количество в граммах:",
            reply_markup=build_cancel_keyboard(),
        )


@router.message(DiaryEditStates.wait_grams)
async def diary_entry_grams_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        grams = parse_entry_grams(message.text or "")
        data = await state.get_data()
        entry = await diary_service(db_session).update_grams(
            current_user.id,
            int(data["edit_entry_id"]),
            grams,
        )
    except (AppError, KeyError) as error:
        await message.answer(
            str(error) if isinstance(error, AppError) else "Данные устарели.",
            reply_markup=build_cancel_keyboard(),
        )
        return
    await state.set_state(None)
    page = int(data.get("edit_page", 1))
    await message.answer(
        entry_text(entry),
        reply_markup=build_entry_actions_keyboard(entry.id, page),
    )


@router.callback_query(DiaryEntryCallback.filter(F.action == "meal"))
async def diary_entry_meal_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите новый приём пищи:",
            reply_markup=build_entry_meal_keyboard(
                callback_data.entry_id,
                callback_data.page,
            ),
        )


@router.callback_query(DiaryEntryMealCallback.filter())
async def diary_entry_meal_save_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryMealCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        entry = await diary_service(db_session).update_meal(
            current_user.id,
            callback_data.entry_id,
            callback_data.meal_type,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    await callback.message.edit_text(
        entry_text(entry),
        reply_markup=build_entry_actions_keyboard(entry.id, callback_data.page),
    )


@router.callback_query(DiaryEntryCallback.filter(F.action == "date"))
async def diary_entry_date_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.update_data(
        edit_entry_id=callback_data.entry_id,
        edit_page=callback_data.page,
    )
    await state.set_state(DiaryEditStates.wait_date)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новую дату в формате ДД.ММ.ГГГГ:",
            reply_markup=build_cancel_keyboard(),
        )


@router.message(DiaryEditStates.wait_date)
async def diary_entry_date_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        entry_date = parse_entry_date(message.text or "")
        data = await state.get_data()
        entry = await diary_service(db_session).update_date(
            current_user.id,
            int(data["edit_entry_id"]),
            entry_date,
        )
    except (AppError, KeyError) as error:
        await message.answer(
            str(error) if isinstance(error, AppError) else "Данные устарели.",
            reply_markup=build_cancel_keyboard(),
        )
        return
    await state.set_state(None)
    await state.update_data(view_date=entry.entry_date.isoformat())
    page = int(data.get("edit_page", 1))
    await message.answer(
        entry_text(entry),
        reply_markup=build_entry_actions_keyboard(entry.id, page),
    )


@router.callback_query(DiaryEntryCallback.filter(F.action == "delete"))
async def diary_entry_delete_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            "Удалить запись из рациона?",
            reply_markup=build_entry_delete_keyboard(
                callback_data.entry_id,
                callback_data.page,
            ),
        )


@router.callback_query(DiaryEntryCallback.filter(F.action == "delete_confirm"))
async def diary_entry_delete_confirm_callback(
    callback: CallbackQuery,
    callback_data: DiaryEntryCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    if callback.message is None:
        return
    try:
        await diary_service(db_session).delete(
            current_user.id,
            callback_data.entry_id,
        )
    except AppError as error:
        await callback.message.edit_text(str(error))
        return
    entry_date = await current_view_date(state, current_user)
    await show_day(
        callback.message,
        state,
        diary_service(db_session),
        current_user.id,
        entry_date,
        edit=True,
    )


@router.callback_query(F.data == DIARY_CANCEL)
async def diary_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Действие отменено. Главное меню")


@router.callback_query(F.data == DIARY_BACK_MAIN)
async def diary_back_main_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")
