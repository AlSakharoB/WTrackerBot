from decimal import Decimal
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import INGREDIENT_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.ingredients import (
    INGREDIENT_CANCEL,
    INGREDIENT_CREATE_RESTART,
    INGREDIENTS_ADD,
    INGREDIENTS_BACK_MAIN,
    INGREDIENTS_LIST,
    INGREDIENTS_NOOP,
    INGREDIENTS_SEARCH,
    IngredientCallback,
    IngredientEditCallback,
    IngredientsPageCallback,
    build_cancel_keyboard,
    build_create_confirmation_keyboard,
    build_delete_confirmation_keyboard,
    build_ingredient_detail_keyboard,
    build_ingredient_edit_keyboard,
    build_ingredient_list_keyboard,
    build_ingredients_menu_keyboard,
    build_search_empty_keyboard,
    build_search_results_keyboard,
)
from app.bot.keyboards.main import INGREDIENTS_BUTTON
from app.bot.states.ingredients import (
    IngredientCreateStates,
    IngredientEditStates,
    IngredientSearchStates,
)
from app.db.models.ingredient import Ingredient
from app.db.models.user import User
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.services.action_lock import generate_action_token
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientPage,
    IngredientService,
    normalize_ingredient_name,
    parse_nutrition_value,
)
from app.services.search import SearchService
from app.utils.decimal import format_decimal

router = Router(name=__name__)

FIELD_PROMPTS = {
    IngredientField.NAME: "Введите новое название:",
    IngredientField.KCAL: "Введите новые калории на 100 г:",
    IngredientField.PROTEIN: "Введите новые белки на 100 г:",
    IngredientField.FAT: "Введите новые жиры на 100 г:",
    IngredientField.CARBS: "Введите новые углеводы на 100 г:",
}

INGREDIENT_SEARCH_PROMPT = """🔎 <b>Поиск ингредиентов</b>

Введите название или часть названия.

Можно писать с небольшой опечаткой.

Например:
«яиный» найдёт «яичный»
«кур груд» найдёт «куриная грудка»"""

INGREDIENT_SEARCH_EMPTY = """Ничего похожего не найдено.

Попробуйте:
• написать меньше слов;
• проверить название;
• создать новый ингредиент."""


def ingredient_service(session: AsyncSession) -> IngredientService:
    return IngredientService(IngredientRepository(session))


def search_service(session: AsyncSession) -> SearchService:
    return SearchService(SearchRepository(session))


def ingredient_card(ingredient: Ingredient) -> str:
    return f"""🥕 <b>{escape(ingredient.name)}</b>

На 100 г:
🔥 {format_decimal(ingredient.kcal_per_100g)} ккал
🥩 Б: {format_decimal(ingredient.protein_per_100g)} г
🥑 Ж: {format_decimal(ingredient.fat_per_100g)} г
🍞 У: {format_decimal(ingredient.carbs_per_100g)} г"""


def ingredient_draft_card(data: dict[str, Any]) -> str:
    return f"""🥕 <b>{escape(str(data["name"]))}</b>

На 100 г:
🔥 {format_decimal(Decimal(str(data["kcal_per_100g"])))} ккал
🥩 Б: {format_decimal(Decimal(str(data["protein_per_100g"])))} г
🥑 Ж: {format_decimal(Decimal(str(data["fat_per_100g"])))} г
🍞 У: {format_decimal(Decimal(str(data["carbs_per_100g"])))} г"""


def ingredient_list_text(page: IngredientPage) -> str:
    if page.total == 0:
        return "У вас пока нет ингредиентов."
    return f"Мои ингредиенты — {page.page}/{page.pages}"


async def send_ingredients_menu(message: Message) -> None:
    await message.answer(
        "🥕 <b>Ингредиенты</b>\n\nСоздавайте и управляйте своими продуктами.",
        reply_markup=build_ingredients_menu_keyboard(),
    )


async def edit_ingredients_menu(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    await callback.message.edit_text(
        "🥕 <b>Ингредиенты</b>\n\nСоздавайте и управляйте своими продуктами.",
        reply_markup=build_ingredients_menu_keyboard(),
    )


async def edit_ingredient_list(
    callback: CallbackQuery,
    service: IngredientService,
    user_id: int,
    page_number: int,
) -> None:
    if callback.message is None:
        return
    page = await service.list_page(user_id, page_number)
    await callback.message.edit_text(
        ingredient_list_text(page),
        reply_markup=build_ingredient_list_keyboard(page),
    )


@router.message(Command("ingredients"))
@router.message(F.text == INGREDIENTS_BUTTON)
async def ingredients_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await send_ingredients_menu(message)


@router.callback_query(F.data == INGREDIENTS_NOOP)
async def ingredients_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "ingredients:menu")
async def ingredients_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await edit_ingredients_menu(callback)


@router.callback_query(F.data == INGREDIENTS_BACK_MAIN)
async def ingredients_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")


@router.callback_query(F.data == INGREDIENTS_LIST)
async def ingredient_list_callback(
    callback: CallbackQuery,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await edit_ingredient_list(
        callback,
        ingredient_service(db_session),
        current_user.id,
        1,
    )


@router.callback_query(IngredientsPageCallback.filter(F.action == "page"))
async def ingredient_page_callback(
    callback: CallbackQuery,
    callback_data: IngredientsPageCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await edit_ingredient_list(
        callback,
        ingredient_service(db_session),
        current_user.id,
        callback_data.page,
    )


@router.callback_query(F.data == INGREDIENTS_ADD)
async def ingredient_add_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(IngredientCreateStates.wait_name)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название ингредиента:",
            reply_markup=build_cancel_keyboard(),
        )


@router.message(IngredientCreateStates.wait_name)
async def ingredient_create_name(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        name, _ = normalize_ingredient_name(message.text or "")
        await ingredient_service(db_session).check_name_available(
            current_user.id,
            name,
        )
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    except DuplicateError as error:
        await state.clear()
        await message.answer(
            f"{escape(str(error))}\n\nДобавление отменено.",
            reply_markup=build_ingredients_menu_keyboard(),
        )
        return
    await state.update_data(name=name)
    await state.set_state(IngredientCreateStates.wait_kcal)
    await message.answer(
        "Ккал на 100 г:",
        reply_markup=build_cancel_keyboard(),
    )


async def process_nutrition_step(
    message: Message,
    state: FSMContext,
    *,
    field: IngredientField,
    next_state: Any,
    next_prompt: str,
) -> None:
    try:
        value = parse_nutrition_value(field, message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await state.update_data(**{field.value: str(value)})
    await state.set_state(next_state)
    await message.answer(next_prompt, reply_markup=build_cancel_keyboard())


@router.message(IngredientCreateStates.wait_kcal)
async def ingredient_create_kcal(message: Message, state: FSMContext) -> None:
    await process_nutrition_step(
        message,
        state,
        field=IngredientField.KCAL,
        next_state=IngredientCreateStates.wait_protein,
        next_prompt="Белки на 100 г:",
    )


@router.message(IngredientCreateStates.wait_protein)
async def ingredient_create_protein(message: Message, state: FSMContext) -> None:
    await process_nutrition_step(
        message,
        state,
        field=IngredientField.PROTEIN,
        next_state=IngredientCreateStates.wait_fat,
        next_prompt="Жиры на 100 г:",
    )


@router.message(IngredientCreateStates.wait_fat)
async def ingredient_create_fat(message: Message, state: FSMContext) -> None:
    await process_nutrition_step(
        message,
        state,
        field=IngredientField.FAT,
        next_state=IngredientCreateStates.wait_carbs,
        next_prompt="Углеводы на 100 г:",
    )


@router.message(IngredientCreateStates.wait_carbs)
async def ingredient_create_carbs(message: Message, state: FSMContext) -> None:
    try:
        value = parse_nutrition_value(IngredientField.CARBS, message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await state.update_data(carbs_per_100g=str(value))
    data = await state.get_data()
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    await state.set_state(IngredientCreateStates.confirm)
    await message.answer(
        f"Проверьте данные:\n\n{ingredient_draft_card(data)}",
        reply_markup=build_create_confirmation_keyboard(action_token),
    )


@router.callback_query(
    IngredientCreateStates.confirm,
    ConfirmActionCallback.filter(F.action == INGREDIENT_SAVE_ACTION),
)
async def ingredient_create_save(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return
    try:
        ingredient = await ingredient_service(db_session).create(
            current_user.id,
            CreateIngredientData(
                name=str(data["name"]),
                kcal_per_100g=Decimal(str(data["kcal_per_100g"])),
                protein_per_100g=Decimal(str(data["protein_per_100g"])),
                fat_per_100g=Decimal(str(data["fat_per_100g"])),
                carbs_per_100g=Decimal(str(data["carbs_per_100g"])),
            ),
        )
    except DuplicateError as error:
        await callback.answer("Добавление отменено", show_alert=True)
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                f"{escape(str(error))}\n\nДобавление отменено.",
                reply_markup=build_ingredients_menu_keyboard(),
            )
        return
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Ингредиент сохранён.\n\n{ingredient_card(ingredient)}",
            reply_markup=build_ingredient_detail_keyboard(ingredient.id, 1),
        )


@router.callback_query(
    IngredientCreateStates.confirm,
    F.data == INGREDIENT_CREATE_RESTART,
)
async def ingredient_create_restart(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(IngredientCreateStates.wait_name)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите данные заново.\n\nНазвание ингредиента:",
            reply_markup=build_cancel_keyboard(),
        )


@router.callback_query(F.data == INGREDIENT_CANCEL)
async def ingredient_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer("Действие отменено")
    await state.clear()
    await edit_ingredients_menu(callback)


@router.callback_query(IngredientCallback.filter(F.action == "view"))
async def ingredient_view_callback(
    callback: CallbackQuery,
    callback_data: IngredientCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        ingredient = await ingredient_service(db_session).get(
            current_user.id,
            callback_data.ingredient_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            ingredient_card(ingredient),
            reply_markup=build_ingredient_detail_keyboard(
                ingredient.id,
                callback_data.page,
            ),
        )


@router.callback_query(IngredientCallback.filter(F.action == "edit"))
async def ingredient_edit_callback(
    callback: CallbackQuery,
    callback_data: IngredientCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        ingredient = await ingredient_service(db_session).get(
            current_user.id,
            callback_data.ingredient_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Что изменить?\n\n{ingredient_card(ingredient)}",
            reply_markup=build_ingredient_edit_keyboard(
                ingredient.id,
                callback_data.page,
            ),
        )


@router.callback_query(IngredientEditCallback.filter())
async def ingredient_edit_field_callback(
    callback: CallbackQuery,
    callback_data: IngredientEditCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(IngredientEditStates.wait_value)
    await state.update_data(
        ingredient_id=callback_data.ingredient_id,
        page=callback_data.page,
        field=callback_data.field.value,
    )
    if callback.message is not None:
        await callback.message.edit_text(
            FIELD_PROMPTS[callback_data.field],
            reply_markup=build_cancel_keyboard(),
        )


@router.message(IngredientEditStates.wait_value)
async def ingredient_edit_value(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    data = await state.get_data()
    field = IngredientField(str(data["field"]))
    try:
        ingredient = await ingredient_service(db_session).update_field(
            current_user.id,
            int(data["ingredient_id"]),
            field,
            message.text or "",
        )
    except (DuplicateError, ValidationError) as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    except NotFoundError as error:
        await state.clear()
        await message.answer(str(error), reply_markup=build_ingredients_menu_keyboard())
        return
    page = int(data["page"])
    await state.clear()
    await message.answer(
        f"Изменения сохранены.\n\n{ingredient_card(ingredient)}",
        reply_markup=build_ingredient_detail_keyboard(ingredient.id, page),
    )


@router.callback_query(IngredientCallback.filter(F.action == "delete"))
async def ingredient_delete_callback(
    callback: CallbackQuery,
    callback_data: IngredientCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        ingredient = await ingredient_service(db_session).get(
            current_user.id,
            callback_data.ingredient_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Удалить ингредиент?\n\n{ingredient_card(ingredient)}",
            reply_markup=build_delete_confirmation_keyboard(
                ingredient.id,
                callback_data.page,
            ),
        )


@router.callback_query(IngredientCallback.filter(F.action == "delete_confirm"))
async def ingredient_delete_confirm_callback(
    callback: CallbackQuery,
    callback_data: IngredientCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    service = ingredient_service(db_session)
    try:
        await service.delete(current_user.id, callback_data.ingredient_id)
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    except ValidationError as error:
        await callback.answer("Удаление невозможно", show_alert=True)
        if callback.message is not None:
            await callback.message.edit_text(
                escape(str(error)),
                reply_markup=build_ingredient_detail_keyboard(
                    callback_data.ingredient_id,
                    callback_data.page,
                ),
            )
        return
    await callback.answer()
    if callback.message is not None:
        page = await service.list_page(current_user.id, callback_data.page)
        await callback.message.edit_text(
            f"Ингредиент удалён.\n\n{ingredient_list_text(page)}",
            reply_markup=build_ingredient_list_keyboard(page),
        )


@router.callback_query(F.data == INGREDIENTS_SEARCH)
async def ingredient_search_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(IngredientSearchStates.wait_query)
    if callback.message is not None:
        await callback.message.edit_text(
            INGREDIENT_SEARCH_PROMPT,
            reply_markup=build_cancel_keyboard(),
        )


@router.message(IngredientSearchStates.wait_query)
async def ingredient_search_query(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        results = await search_service(db_session).search_ingredients(
            current_user.id,
            message.text or "",
        )
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_cancel_keyboard())
        return
    await state.clear()
    if not results:
        await message.answer(
            INGREDIENT_SEARCH_EMPTY,
            reply_markup=build_search_empty_keyboard(),
        )
        return
    await message.answer(
        "🔎 <b>Результаты</b>",
        reply_markup=build_search_results_keyboard(results),
    )
