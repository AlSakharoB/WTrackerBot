from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import dishes as dish_handlers
from app.bot.handlers.dishes import (
    DISH_SEARCH_EMPTY,
    DISH_SEARCH_PROMPT,
    dishes_search,
    dishes_search_query,
)
from app.bot.keyboards.dishes import (
    DISHES_CREATE,
    DISHES_MENU,
    DISHES_SEARCH,
    DishCallback,
    build_dish_search_empty_keyboard,
    build_dish_search_results_keyboard,
)
from app.bot.states.dishes import DishSearchStates
from app.db.models.user import User
from app.search import SearchResult


def search_results() -> list[SearchResult]:
    return [
        SearchResult(21, "Яичный омлет", Decimal("94.5")),
        SearchResult(22, "Омлет с сыром", Decimal("41.2")),
    ]


def test_dish_search_results_open_dish_cards() -> None:
    keyboard = build_dish_search_results_keyboard(search_results())

    assert [row[0].text for row in keyboard.inline_keyboard] == [
        "🍲 Яичный омлет",
        "🍲 Омлет с сыром",
        "🔎 Искать снова",
        "⬅️ Назад",
    ]
    first_callback = DishCallback.unpack(
        keyboard.inline_keyboard[0][0].callback_data or ""
    )
    assert first_callback.action == "view"
    assert first_callback.dish_id == 21


def test_dish_search_empty_keyboard_has_required_actions() -> None:
    keyboard = build_dish_search_empty_keyboard()

    assert [row[0].text for row in keyboard.inline_keyboard] == [
        "➕ Создать блюдо",
        "🔎 Искать снова",
        "⬅️ Назад",
    ]
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        DISHES_CREATE,
        DISHES_SEARCH,
        DISHES_MENU,
    ]


async def test_dish_search_callback_shows_fuzzy_prompt() -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = AsyncMock(spec=Message)
    callback.message.edit_text = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await dishes_search(callback, state)

    state.clear.assert_awaited_once()
    state.set_state.assert_awaited_once_with(DishSearchStates.wait_query)
    assert callback.message.edit_text.await_args.args[0] == DISH_SEARCH_PROMPT
    assert "яиный омл" in DISH_SEARCH_PROMPT
    assert "кур греч" in DISH_SEARCH_PROMPT


async def test_dish_search_query_renders_ranked_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = AsyncMock(spec=Message)
    message.text = "яиный омл"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    service.search_dishes = AsyncMock(return_value=search_results())
    monkeypatch.setattr(dish_handlers, "search_service", lambda session: service)

    await dishes_search_query(
        message,
        state,
        current_user=User(id=9, telegram_id=99, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    service.search_dishes.assert_awaited_once_with(9, "яиный омл")
    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0] == "🔎 <b>Результаты</b>"
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "🍲 Яичный омлет"


async def test_dish_search_query_renders_actionable_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = AsyncMock(spec=Message)
    message.text = "несуществующее блюдо"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    service.search_dishes = AsyncMock(return_value=[])
    monkeypatch.setattr(dish_handlers, "search_service", lambda session: service)

    await dishes_search_query(
        message,
        state,
        current_user=User(id=9, telegram_id=99, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    assert message.answer.await_args.args[0] == DISH_SEARCH_EMPTY
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].callback_data == DISHES_CREATE
