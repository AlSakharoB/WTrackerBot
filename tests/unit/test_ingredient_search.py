from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import ingredients as ingredient_handlers
from app.bot.handlers.ingredients import (
    INGREDIENT_SEARCH_EMPTY,
    INGREDIENT_SEARCH_PROMPT,
    ingredient_search_callback,
    ingredient_search_query,
)
from app.bot.keyboards.ingredients import (
    INGREDIENTS_ADD,
    INGREDIENTS_SEARCH,
    IngredientCallback,
    build_search_empty_keyboard,
    build_search_results_keyboard,
)
from app.bot.states.ingredients import IngredientSearchStates
from app.db.models.user import User
from app.search import SearchResult


def search_results() -> list[SearchResult]:
    return [
        SearchResult(11, "Яичный белок", Decimal("72.5")),
        SearchResult(12, "Яичный салат", Decimal("68.2")),
    ]


def test_search_results_keyboard_opens_ingredient_cards() -> None:
    keyboard = build_search_results_keyboard(search_results())

    assert [row[0].text for row in keyboard.inline_keyboard] == [
        "🥕 Яичный белок",
        "🥕 Яичный салат",
        "🔎 Искать снова",
        "⬅️ Назад",
    ]
    first_callback = IngredientCallback.unpack(
        keyboard.inline_keyboard[0][0].callback_data or ""
    )
    assert first_callback.action == "view"
    assert first_callback.ingredient_id == 11


def test_search_empty_keyboard_has_all_required_actions() -> None:
    keyboard = build_search_empty_keyboard()

    assert [row[0].text for row in keyboard.inline_keyboard] == [
        "➕ Создать ингредиент",
        "🔎 Искать снова",
        "⬅️ Назад",
    ]
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        INGREDIENTS_ADD,
        INGREDIENTS_SEARCH,
        "ingredients:menu",
    ]


async def test_search_callback_shows_fuzzy_search_prompt() -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await ingredient_search_callback(callback, state)

    state.clear.assert_awaited_once()
    state.set_state.assert_awaited_once_with(IngredientSearchStates.wait_query)
    callback.message.edit_text.assert_awaited_once()
    assert callback.message.edit_text.await_args.args[0] == INGREDIENT_SEARCH_PROMPT
    assert "яиный" in INGREDIENT_SEARCH_PROMPT
    assert "кур груд" in INGREDIENT_SEARCH_PROMPT


async def test_search_query_renders_ranked_results(monkeypatch: object) -> None:
    message = AsyncMock(spec=Message)
    message.text = "яиный"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    service.search_ingredients = AsyncMock(return_value=search_results())
    monkeypatch.setattr(  # type: ignore[union-attr]
        ingredient_handlers,
        "search_service",
        lambda session: service,
    )

    await ingredient_search_query(
        message,
        state,
        current_user=User(id=7, telegram_id=77, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    service.search_ingredients.assert_awaited_once_with(7, "яиный")
    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0] == "🔎 <b>Результаты</b>"
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "🥕 Яичный белок"


async def test_search_query_renders_actionable_empty_state(
    monkeypatch: object,
) -> None:
    message = AsyncMock(spec=Message)
    message.text = "несуществующий"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    service.search_ingredients = AsyncMock(return_value=[])
    monkeypatch.setattr(  # type: ignore[union-attr]
        ingredient_handlers,
        "search_service",
        lambda session: service,
    )

    await ingredient_search_query(
        message,
        state,
        current_user=User(id=7, telegram_id=77, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    assert message.answer.await_args.args[0] == INGREDIENT_SEARCH_EMPTY
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == INGREDIENTS_ADD
