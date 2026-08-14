from unittest.mock import AsyncMock

from aiogram.types import Message

from app.bot.handlers.start import MENU_TEXT, WELCOME_TEXT, menu_handler, start_handler
from app.bot.keyboards.main import (
    ADD_FOOD_BUTTON,
    DISHES_BUTTON,
    GOAL_BUTTON,
    HELP_BUTTON,
    INGREDIENTS_BUTTON,
    SETTINGS_BUTTON,
    TODAY_BUTTON,
    WEIGHT_BUTTON,
    build_main_menu_keyboard,
)
from app.db.models.user import User


def test_main_menu_contains_expected_layout() -> None:
    keyboard = build_main_menu_keyboard()

    assert [[button.text for button in row] for row in keyboard.keyboard] == [
        [TODAY_BUTTON],
        [ADD_FOOD_BUTTON, INGREDIENTS_BUTTON],
        [DISHES_BUTTON, WEIGHT_BUTTON],
        [GOAL_BUTTON, SETTINGS_BUTTON],
        [HELP_BUTTON],
    ]
    assert keyboard.is_persistent is True
    assert keyboard.resize_keyboard is True


async def test_start_greets_new_user() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()
    user = User(id=1, telegram_id=123, timezone="Europe/Moscow")

    await start_handler(message, current_user=user, is_new_user=True, state=state)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == WELCOME_TEXT


async def test_start_opens_menu_for_existing_user() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()
    user = User(id=1, telegram_id=123, timezone="Europe/Moscow")

    await start_handler(message, current_user=user, is_new_user=False, state=state)

    assert message.answer.await_args.args[0] == MENU_TEXT


async def test_menu_command_shows_keyboard() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()
    user = User(id=1, telegram_id=123, timezone="Europe/Moscow")

    await menu_handler(message, current_user=user, state=state)

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert message.answer.await_args.args[0] == MENU_TEXT
    assert message.answer.await_args.kwargs["reply_markup"].is_persistent is True
