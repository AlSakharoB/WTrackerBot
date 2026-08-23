from decimal import Decimal
from html import escape
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import confirmation_data
from app.bot.keyboards.actions import DISH_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.dishes import (
    DISH_EDITOR_ADD,
    DISH_EDITOR_CANCEL,
    DISH_EDITOR_CHANGE,
    DISH_EDITOR_INGREDIENT_SEARCH,
    DISH_EDITOR_REMOVE,
    DISH_EDITOR_RENAME,
    DISHES_BACK_MAIN,
    DISHES_CREATE,
    DISHES_LIST,
    DISHES_MENU,
    DISHES_NOOP,
    DISHES_SEARCH,
    DishCallback,
    DishesPageCallback,
    DishIngredientCallback,
    DishIngredientPageCallback,
    build_component_picker_keyboard,
    build_dish_cancel_keyboard,
    build_dish_composition_keyboard,
    build_dish_delete_keyboard,
    build_dish_detail_keyboard,
    build_dish_editor_keyboard,
    build_dish_list_keyboard,
    build_dish_search_empty_keyboard,
    build_dish_search_results_keyboard,
    build_dishes_menu_keyboard,
    build_ingredient_picker_keyboard,
    build_ingredient_search_prompt_keyboard,
    build_ingredient_search_results_keyboard,
)
from app.bot.keyboards.main import DISHES_BUTTON
from app.bot.states.dishes import DishEditorStates, DishSearchStates
from app.db.models.user import User
from app.exceptions import AppError, DuplicateError, NotFoundError, ValidationError
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.services.action_lock import generate_action_token
from app.services.dishes import (
    DishComponent,
    DishComponentData,
    DishDetails,
    DishPage,
    DishPreview,
    DishService,
    normalize_dish_name,
    parse_component_grams,
)
from app.services.ingredients import IngredientService
from app.services.search import SearchService
from app.utils.decimal import format_decimal

router = Router(name=__name__)

DISH_SEARCH_PROMPT = """🔎 <b>Поиск блюд</b>

Введите название или часть названия блюда.

Можно писать с небольшой опечаткой.

Например:
«яиный омл» найдёт «яичный омлет»
«кур греч» найдёт «курица с гречкой»"""

DISH_SEARCH_EMPTY = """Ничего похожего не найдено.

Попробуйте:
• написать меньше слов;
• проверить название;
• создать новое блюдо."""

DISH_INGREDIENT_SEARCH_PROMPT = """🔎 <b>Поиск ингредиента</b>

Введите название или часть названия.

Можно писать с небольшой опечаткой."""

DISH_INGREDIENT_SEARCH_EMPTY = """Ничего похожего не найдено.

Попробуйте изменить запрос или вернуться ко всем ингредиентам."""


def dish_service(session: AsyncSession) -> DishService:
    return DishService(DishRepository(session))


def search_service(session: AsyncSession) -> SearchService:
    return SearchService(SearchRepository(session))


def draft_components(data: dict[str, Any]) -> list[DishComponentData]:
    return [
        DishComponentData(
            ingredient_id=int(item["ingredient_id"]),
            grams=Decimal(str(item["grams"])),
        )
        for item in data.get("components", [])
    ]


def serialize_components(
    components: list[DishComponentData],
) -> list[dict[str, str | int]]:
    return [
        {"ingredient_id": item.ingredient_id, "grams": str(item.grams)}
        for item in components
    ]


def nutrition_text(nutrition: Any) -> str:
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


def composition_text(components: list[DishComponent]) -> str:
    return "\n".join(
        f"• {escape(item.ingredient.name)} — {format_decimal(item.grams)} г"
        for item in components
    )


def dish_card(details: DishDetails) -> str:
    return (
        f"🍲 <b>{escape(details.dish.name)}</b>\n\n{nutrition_text(details.nutrition)}"
    )


def dish_composition_card(details: DishDetails) -> str:
    return (
        f"🍲 <b>{escape(details.dish.name)}</b>\n\n"
        f"Состав:\n{composition_text(details.components)}\n\n"
        f"{nutrition_text(details.nutrition)}"
    )


def dish_preview_card(preview: DishPreview) -> str:
    return (
        f"🍲 <b>{escape(preview.name)}</b>\n\n"
        f"Состав:\n{composition_text(preview.components)}\n\n"
        f"{nutrition_text(preview.nutrition)}"
    )


def dish_list_text(page: DishPage) -> str:
    if page.total == 0:
        return "У вас пока нет блюд."
    return f"Мои блюда — {page.page}/{page.pages}"


async def build_preview(
    state: FSMContext,
    current_user: User,
    session: AsyncSession,
) -> DishPreview | None:
    data = await state.get_data()
    components = draft_components(data)
    if not components:
        return None
    return await dish_service(session).preview(
        current_user.id,
        str(data["name"]),
        components,
    )


async def show_editor_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    session: AsyncSession,
    *,
    edit: bool,
) -> None:
    data = await state.get_data()
    preview = await build_preview(state, current_user, session)
    if preview is None:
        text = (
            f"🍲 <b>{escape(str(data['name']))}</b>\n\n"
            "Добавьте хотя бы один ингредиент."
        )
    else:
        text = dish_preview_card(preview)
    action_token = generate_action_token()
    await state.update_data(action_token=action_token)
    markup = build_dish_editor_keyboard(preview is not None, action_token)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def edit_dishes_menu(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.edit_text(
            "🍲 <b>Блюда</b>\n\nСобирайте рецепты из своих ингредиентов.",
            reply_markup=build_dishes_menu_keyboard(),
        )


async def edit_dish_list(
    callback: CallbackQuery,
    service: DishService,
    user_id: int,
    page_number: int,
) -> None:
    if callback.message is None:
        return
    page = await service.list_page(user_id, page_number)
    await callback.message.edit_text(
        dish_list_text(page),
        reply_markup=build_dish_list_keyboard(page),
    )


@router.message(Command("dishes"))
@router.message(F.text == DISHES_BUTTON)
async def dishes_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🍲 <b>Блюда</b>\n\nСобирайте рецепты из своих ингредиентов.",
        reply_markup=build_dishes_menu_keyboard(),
    )


@router.callback_query(F.data == DISHES_MENU)
async def dishes_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await edit_dishes_menu(callback)


@router.callback_query(F.data == DISHES_BACK_MAIN)
async def dishes_back_main(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Главное меню")


@router.callback_query(F.data == DISHES_NOOP)
async def dishes_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == DISHES_LIST)
async def dishes_list_callback(
    callback: CallbackQuery,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await edit_dish_list(callback, dish_service(db_session), current_user.id, 1)


@router.callback_query(DishesPageCallback.filter(F.action == "page"))
async def dishes_page_callback(
    callback: CallbackQuery,
    callback_data: DishesPageCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await edit_dish_list(
        callback,
        dish_service(db_session),
        current_user.id,
        callback_data.page,
    )


@router.callback_query(F.data == DISHES_CREATE)
async def dish_create_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.update_data(mode="create", dish_id=None, page=1, components=[])
    await state.set_state(DishEditorStates.wait_name)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название блюда:",
            reply_markup=build_dish_cancel_keyboard(),
        )


@router.message(DishEditorStates.wait_name)
async def dish_name_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        name, _ = normalize_dish_name(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_dish_cancel_keyboard())
        return
    data = await state.get_data()
    if data.get("mode") == "create":
        try:
            await dish_service(db_session).check_name_available(current_user.id, name)
        except DuplicateError as error:
            await state.clear()
            await message.answer(
                f"{escape(str(error))}\n\nДобавление отменено.",
                reply_markup=build_dishes_menu_keyboard(),
            )
            return
    await state.update_data(name=name)
    await state.set_state(DishEditorStates.editor)
    await show_editor_message(
        message,
        state,
        current_user,
        db_session,
        edit=False,
    )


@router.callback_query(DishEditorStates.editor, F.data == DISH_EDITOR_RENAME)
async def dish_editor_rename(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(DishEditorStates.wait_name)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новое название блюда:",
            reply_markup=build_dish_cancel_keyboard(),
        )


@router.callback_query(DishEditorStates.editor, F.data == DISH_EDITOR_ADD)
async def dish_editor_add(
    callback: CallbackQuery,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    page = await IngredientService(IngredientRepository(db_session)).list_page(
        current_user.id,
        1,
    )
    if callback.message is not None:
        text = "Выберите ингредиент:" if page.total else "Сначала создайте ингредиент."
        await callback.message.edit_text(
            text,
            reply_markup=build_ingredient_picker_keyboard(page),
        )


@router.callback_query(
    DishEditorStates.wait_ingredient_search,
    F.data == DISH_EDITOR_ADD,
)
async def dish_ingredient_search_open_list(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.set_state(DishEditorStates.editor)
    await dish_editor_add(callback, current_user, db_session)


@router.callback_query(
    DishEditorStates.editor,
    F.data == DISH_EDITOR_INGREDIENT_SEARCH,
)
async def dish_ingredient_search(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.set_state(DishEditorStates.wait_ingredient_search)
    if callback.message is not None:
        await callback.message.edit_text(
            DISH_INGREDIENT_SEARCH_PROMPT,
            reply_markup=build_ingredient_search_prompt_keyboard(),
        )


@router.message(DishEditorStates.wait_ingredient_search)
async def dish_ingredient_search_query(
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
        await message.answer(
            str(error),
            reply_markup=build_ingredient_search_prompt_keyboard(),
        )
        return
    await state.set_state(DishEditorStates.editor)
    if not results:
        await message.answer(
            DISH_INGREDIENT_SEARCH_EMPTY,
            reply_markup=build_ingredient_search_results_keyboard([]),
        )
        return
    await message.answer(
        "🔎 <b>Найденные ингредиенты</b>",
        reply_markup=build_ingredient_search_results_keyboard(results),
    )


@router.callback_query(
    DishEditorStates.editor,
    DishIngredientPageCallback.filter(),
)
async def dish_ingredient_page(
    callback: CallbackQuery,
    callback_data: DishIngredientPageCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    page = await IngredientService(IngredientRepository(db_session)).list_page(
        current_user.id,
        callback_data.page,
    )
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите ингредиент:",
            reply_markup=build_ingredient_picker_keyboard(page),
        )


@router.callback_query(
    DishEditorStates.editor,
    DishIngredientCallback.filter(F.action == "select"),
)
async def dish_ingredient_select(
    callback: CallbackQuery,
    callback_data: DishIngredientCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        ingredient = await IngredientService(IngredientRepository(db_session)).get(
            current_user.id,
            callback_data.ingredient_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    await state.update_data(pending_ingredient_id=ingredient.id)
    await state.set_state(DishEditorStates.wait_ingredient_grams)
    if callback.message is not None:
        await callback.message.edit_text(
            f"Сколько граммов «{escape(ingredient.name)}» добавить?",
            reply_markup=build_dish_cancel_keyboard(),
        )


@router.message(DishEditorStates.wait_ingredient_grams)
async def dish_ingredient_grams(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        grams = parse_component_grams(message.text or "")
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_dish_cancel_keyboard())
        return
    data = await state.get_data()
    ingredient_id = int(data["pending_ingredient_id"])
    components = draft_components(data)
    updated = False
    for index, component in enumerate(components):
        if component.ingredient_id == ingredient_id:
            components[index] = DishComponentData(ingredient_id, grams)
            updated = True
            break
    if not updated:
        components.append(DishComponentData(ingredient_id, grams))
    await state.update_data(
        components=serialize_components(components),
        pending_ingredient_id=None,
    )
    await state.set_state(DishEditorStates.editor)
    await show_editor_message(
        message,
        state,
        current_user,
        db_session,
        edit=False,
    )


@router.callback_query(DishEditorStates.editor, F.data == DISH_EDITOR_CHANGE)
async def dish_editor_change(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    preview = await build_preview(state, current_user, db_session)
    if callback.message is not None and preview is not None:
        await callback.message.edit_text(
            "Выберите ингредиент для изменения граммовки:",
            reply_markup=build_component_picker_keyboard(preview.components, "change"),
        )


@router.callback_query(
    DishEditorStates.editor,
    DishIngredientCallback.filter(F.action == "change"),
)
async def dish_component_change(
    callback: CallbackQuery,
    callback_data: DishIngredientCallback,
    state: FSMContext,
) -> None:
    await callback.answer()
    await state.update_data(pending_ingredient_id=callback_data.ingredient_id)
    await state.set_state(DishEditorStates.wait_ingredient_grams)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите новую граммовку:",
            reply_markup=build_dish_cancel_keyboard(),
        )


@router.callback_query(DishEditorStates.editor, F.data == DISH_EDITOR_REMOVE)
async def dish_editor_remove(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    preview = await build_preview(state, current_user, db_session)
    if callback.message is not None and preview is not None:
        await callback.message.edit_text(
            "Что удалить из состава?",
            reply_markup=build_component_picker_keyboard(preview.components, "remove"),
        )


@router.callback_query(
    DishEditorStates.editor,
    DishIngredientCallback.filter(F.action == "remove"),
)
async def dish_component_remove(
    callback: CallbackQuery,
    callback_data: DishIngredientCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer("Ингредиент удалён из рецепта")
    data = await state.get_data()
    components = [
        item
        for item in draft_components(data)
        if item.ingredient_id != callback_data.ingredient_id
    ]
    await state.update_data(components=serialize_components(components))
    await state.set_state(DishEditorStates.editor)
    if callback.message is not None:
        await show_editor_message(
            callback.message,
            state,
            current_user,
            db_session,
            edit=True,
        )


@router.callback_query(DishEditorStates.editor, F.data == "dish_editor:back")
async def dish_editor_back(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer()
    await state.set_state(DishEditorStates.editor)
    if callback.message is not None:
        await show_editor_message(
            callback.message,
            state,
            current_user,
            db_session,
            edit=True,
        )


@router.callback_query(
    DishEditorStates.wait_ingredient_search,
    F.data == "dish_editor:back",
)
async def dish_ingredient_search_back(
    callback: CallbackQuery,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await state.set_state(DishEditorStates.editor)
    await dish_editor_back(callback, state, current_user, db_session)


@router.callback_query(
    DishEditorStates.editor,
    ConfirmActionCallback.filter(F.action == DISH_SAVE_ACTION),
)
async def dish_editor_save(
    callback: CallbackQuery,
    callback_data: ConfirmActionCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    data = await confirmation_data(callback, state, callback_data.token)
    if data is None:
        return
    service = dish_service(db_session)
    try:
        if data["mode"] == "create":
            details = await service.create(
                current_user.id,
                str(data["name"]),
                draft_components(data),
            )
        else:
            details = await service.replace(
                current_user.id,
                int(data["dish_id"]),
                str(data["name"]),
                draft_components(data),
            )
    except DuplicateError as error:
        if data["mode"] != "create":
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer("Добавление отменено", show_alert=True)
        await state.clear()
        if callback.message is not None:
            await callback.message.edit_text(
                f"{escape(str(error))}\n\nДобавление отменено.",
                reply_markup=build_dishes_menu_keyboard(),
            )
        return
    except AppError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Блюдо сохранено")
    page = int(data["page"])
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            dish_card(details),
            reply_markup=build_dish_detail_keyboard(details.dish.id, page),
        )


@router.callback_query(F.data == DISH_EDITOR_CANCEL)
async def dish_editor_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Редактирование отменено")
    await state.clear()
    await edit_dishes_menu(callback)


@router.callback_query(DishCallback.filter(F.action == "view"))
async def dish_view(
    callback: CallbackQuery,
    callback_data: DishCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        details = await dish_service(db_session).get(
            current_user.id,
            callback_data.dish_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            dish_card(details),
            reply_markup=build_dish_detail_keyboard(
                details.dish.id,
                callback_data.page,
            ),
        )


@router.callback_query(DishCallback.filter(F.action == "composition"))
async def dish_composition(
    callback: CallbackQuery,
    callback_data: DishCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        details = await dish_service(db_session).get(
            current_user.id,
            callback_data.dish_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            dish_composition_card(details),
            reply_markup=build_dish_composition_keyboard(
                details.dish.id,
                callback_data.page,
            ),
        )


@router.callback_query(DishCallback.filter(F.action == "edit"))
async def dish_edit(
    callback: CallbackQuery,
    callback_data: DishCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        details = await dish_service(db_session).get(
            current_user.id,
            callback_data.dish_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    await state.clear()
    await state.update_data(
        mode="edit",
        dish_id=details.dish.id,
        page=callback_data.page,
        name=details.dish.name,
        components=serialize_components(
            [
                DishComponentData(item.ingredient.id, item.grams)
                for item in details.components
            ]
        ),
    )
    await state.set_state(DishEditorStates.editor)
    if callback.message is not None:
        await show_editor_message(
            callback.message,
            state,
            current_user,
            db_session,
            edit=True,
        )


@router.callback_query(DishCallback.filter(F.action == "delete"))
async def dish_delete(
    callback: CallbackQuery,
    callback_data: DishCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        details = await dish_service(db_session).get(
            current_user.id,
            callback_data.dish_id,
        )
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Удалить блюдо?\n\n{dish_card(details)}",
            reply_markup=build_dish_delete_keyboard(
                details.dish.id,
                callback_data.page,
            ),
        )


@router.callback_query(DishCallback.filter(F.action == "delete_confirm"))
async def dish_delete_confirm(
    callback: CallbackQuery,
    callback_data: DishCallback,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    service = dish_service(db_session)
    try:
        await service.delete(current_user.id, callback_data.dish_id)
    except NotFoundError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Блюдо удалено")
    if callback.message is not None:
        page = await service.list_page(current_user.id, callback_data.page)
        await callback.message.edit_text(
            dish_list_text(page),
            reply_markup=build_dish_list_keyboard(page),
        )


@router.callback_query(F.data == DISHES_SEARCH)
async def dishes_search(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(DishSearchStates.wait_query)
    if callback.message is not None:
        await callback.message.edit_text(
            DISH_SEARCH_PROMPT,
            reply_markup=build_dish_cancel_keyboard(),
        )


@router.message(DishSearchStates.wait_query)
async def dishes_search_query(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        results = await search_service(db_session).search_dishes(
            current_user.id,
            message.text or "",
        )
    except ValidationError as error:
        await message.answer(str(error), reply_markup=build_dish_cancel_keyboard())
        return
    await state.clear()
    if not results:
        await message.answer(
            DISH_SEARCH_EMPTY,
            reply_markup=build_dish_search_empty_keyboard(),
        )
        return
    await message.answer(
        "🔎 <b>Результаты</b>",
        reply_markup=build_dish_search_results_keyboard(results),
    )
