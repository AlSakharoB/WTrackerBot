from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import Message

from app.bot.handlers.settings import (
    about_screen,
    app_version,
    delete_phrase_message,
    diary_behavior_screen,
    diary_behavior_text,
    display_screen,
    number_format_text,
    privacy_screen,
    settings_back_main,
    settings_handler,
    timezone_screen,
)
from app.bot.keyboards.settings import (
    SETTINGS_ABOUT,
    SETTINGS_BACK_MAIN,
    SETTINGS_DIARY,
    SETTINGS_DISPLAY,
    SETTINGS_NUTRITION_GOALS,
    SETTINGS_PRIVACY,
    SETTINGS_REMINDERS,
    SETTINGS_TIMEZONE,
    build_diary_behavior_keyboard,
    build_number_format_keyboard,
    build_settings_menu_keyboard,
    build_timezone_keyboard,
)
from app.db.models.user import User
from app.services.settings import POPULAR_TIMEZONES
from app.user_settings import AfterFoodAddAction, NumberFormat


def test_settings_menu_contains_all_working_sections() -> None:
    keyboard = build_settings_menu_keyboard()
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert callbacks == [
        SETTINGS_TIMEZONE,
        SETTINGS_DISPLAY,
        SETTINGS_DIARY,
        SETTINGS_NUTRITION_GOALS,
        SETTINGS_REMINDERS,
        SETTINGS_PRIVACY,
        SETTINGS_ABOUT,
        SETTINGS_BACK_MAIN,
    ]


def test_timezone_keyboard_marks_current_and_lists_popular_zones() -> None:
    keyboard = build_timezone_keyboard("Europe/Berlin")

    assert len(keyboard.inline_keyboard) == len(POPULAR_TIMEZONES) + 1
    assert keyboard.inline_keyboard[1][0].text == "✓ Europe/Berlin"
    assert all(
        len((row[0].callback_data or "").encode()) <= 64
        for row in keyboard.inline_keyboard[:-1]
    )


def test_number_and_diary_keyboards_mark_selected_values() -> None:
    numbers = build_number_format_keyboard(NumberFormat.ONE_DECIMAL)
    diary = build_diary_behavior_keyboard(AfterFoodAddAction.STAY)

    assert numbers.inline_keyboard[1][0].text == "✓ 1 знак"
    assert diary.inline_keyboard[1][0].text == "✓ Остаться в текущем разделе"
    assert "1 знак" in number_format_text(NumberFormat.ONE_DECIMAL)
    assert "Остаться" in diary_behavior_text(AfterFoodAddAction.STAY)


async def test_settings_button_opens_inline_menu() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock()

    await settings_handler(message, state)

    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0].startswith("⚙️")
    assert message.answer.await_args.kwargs["reply_markup"] == (
        build_settings_menu_keyboard()
    )


async def test_all_visible_settings_sections_open() -> None:
    callback = AsyncMock()
    callback.message = AsyncMock()
    state = AsyncMock()
    user = User(
        id=1,
        telegram_id=11,
        timezone="Europe/Moscow",
        number_format=NumberFormat.AUTOMATIC,
        after_food_add_action=AfterFoodAddAction.OPEN_TODAY,
    )

    await timezone_screen(callback, user)
    await display_screen(callback, user)
    await diary_behavior_screen(callback, user)
    await privacy_screen(callback, state)
    await about_screen(callback, "production")
    await settings_back_main(callback, state)

    assert callback.message.edit_text.await_count == 6
    callback.message.answer.assert_awaited_once()


def test_about_version_is_safe_public_value() -> None:
    assert app_version() == "0.1.0"
    about = SimpleNamespace(version=app_version(), environment="production")
    assert "postgresql" not in repr(about).lower()
    assert "token" not in repr(about).lower()


async def test_wrong_delete_phrase_cancels_without_deleting() -> None:
    message = AsyncMock(spec=Message)
    message.text = "удалить"
    message.answer = AsyncMock()
    state = AsyncMock()
    service = AsyncMock()
    user = User(id=7, telegram_id=77, timezone="Europe/Moscow")

    with patch(
        "app.bot.handlers.settings.privacy_service",
        return_value=service,
    ):
        await delete_phrase_message(
            message,
            state,
            user,
            AsyncMock(),
            "Europe/Moscow",
        )

    service.clear_user_data.assert_not_awaited()
    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0] == "Удаление отменено."


async def test_exact_delete_phrase_uses_current_user_only() -> None:
    message = AsyncMock(spec=Message)
    message.text = "УДАЛИТЬ"
    message.answer = AsyncMock()
    state = AsyncMock()
    service = AsyncMock()
    user = User(id=8, telegram_id=88, timezone="Europe/Moscow")

    with patch(
        "app.bot.handlers.settings.privacy_service",
        return_value=service,
    ):
        await delete_phrase_message(
            message,
            state,
            user,
            AsyncMock(),
            "Europe/Moscow",
        )

    service.clear_user_data.assert_awaited_once_with(8)
    state.clear.assert_awaited_once()
