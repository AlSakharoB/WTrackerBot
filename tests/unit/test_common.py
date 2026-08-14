from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Message

from app.bot.handlers.common import (
    FALLBACK_TEXT,
    HELP_TEXT,
    callback_fallback_handler,
    global_error_handler,
    help_handler,
    message_fallback_handler,
)
from app.exceptions import ValidationError


async def test_help_clears_state_and_shows_main_keyboard() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()

    await help_handler(message, state)

    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0] == HELP_TEXT
    assert message.answer.await_args.kwargs["reply_markup"].is_persistent is True


async def test_message_fallback_distinguishes_active_flow() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)

    await message_fallback_handler(message, state)
    assert message.answer.await_args.args[0] == FALLBACK_TEXT

    state.get_state = AsyncMock(return_value="editor:wait_value")
    await message_fallback_handler(message, state)
    assert "/cancel" in message.answer.await_args.args[0]


async def test_unknown_callback_gets_stale_button_alert() -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()

    await callback_fallback_handler(callback)

    callback.answer.assert_awaited_once_with(
        "Кнопка устарела. Откройте раздел заново.",
        show_alert=True,
    )


async def test_global_error_handler_reports_domain_error() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    event = SimpleNamespace(
        exception=ValidationError("Некорректное значение."),
        update=SimpleNamespace(
            update_id=123,
            message=message,
            callback_query=None,
        ),
    )

    handled = await global_error_handler(event)  # type: ignore[arg-type]

    assert handled is True
    assert message.answer.await_args.args[0] == "Некорректное значение."
