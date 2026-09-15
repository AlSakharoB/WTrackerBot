from unittest.mock import AsyncMock, Mock, call

from aiogram.types import MenuButtonCommands, MenuButtonWebApp

from app.services.miniapp_rollout import (
    MiniAppRollout,
    reconcile_miniapp_menu_button,
)


def make_rollout(**overrides: object) -> MiniAppRollout:
    values: dict[str, object] = {
        "enabled": True,
        "public_url": "https://app.example.com",
        "allowed_telegram_ids": frozenset(),
        "manage_menu_button": True,
        "menu_button_text": "Открыть дневник",
    }
    values.update(overrides)
    return MiniAppRollout(**values)  # type: ignore[arg-type]


async def test_menu_button_management_can_be_disabled() -> None:
    bot = Mock(set_chat_menu_button=AsyncMock())

    await reconcile_miniapp_menu_button(
        bot,
        make_rollout(manage_menu_button=False),
    )

    bot.set_chat_menu_button.assert_not_awaited()


async def test_disabled_miniapp_restores_commands_menu() -> None:
    bot = Mock(set_chat_menu_button=AsyncMock())

    await reconcile_miniapp_menu_button(
        bot,
        make_rollout(
            enabled=False,
            allowed_telegram_ids=frozenset({222, 111}),
        ),
    )

    assert bot.set_chat_menu_button.await_args_list == [
        call(menu_button=MenuButtonCommands()),
        call(chat_id=111, menu_button=MenuButtonCommands()),
        call(chat_id=222, menu_button=MenuButtonCommands()),
    ]


async def test_allowlist_keeps_default_commands_and_sets_private_buttons() -> None:
    bot = Mock(set_chat_menu_button=AsyncMock())

    await reconcile_miniapp_menu_button(
        bot,
        make_rollout(allowed_telegram_ids=frozenset({222, 111})),
    )

    calls = bot.set_chat_menu_button.await_args_list
    assert isinstance(calls[0].kwargs["menu_button"], MenuButtonCommands)
    assert [item.kwargs.get("chat_id") for item in calls] == [None, 111, 222]
    for item in calls[1:]:
        button = item.kwargs["menu_button"]
        assert isinstance(button, MenuButtonWebApp)
        assert button.text == "Открыть дневник"
        assert button.web_app.url == "https://app.example.com"


async def test_empty_allowlist_sets_global_web_app_button() -> None:
    bot = Mock(set_chat_menu_button=AsyncMock())

    await reconcile_miniapp_menu_button(bot, make_rollout())

    bot.set_chat_menu_button.assert_awaited_once()
    call_kwargs = bot.set_chat_menu_button.await_args.kwargs
    assert "chat_id" not in call_kwargs
    button = call_kwargs["menu_button"]
    assert isinstance(button, MenuButtonWebApp)
    assert button.web_app.url == "https://app.example.com"


async def test_reconciliation_is_idempotent_across_restarts() -> None:
    bot = Mock(set_chat_menu_button=AsyncMock())
    rollout = make_rollout(allowed_telegram_ids=frozenset({111}))

    await reconcile_miniapp_menu_button(bot, rollout)
    first_run = list(bot.set_chat_menu_button.await_args_list)
    bot.set_chat_menu_button.reset_mock()
    await reconcile_miniapp_menu_button(bot, rollout)

    assert bot.set_chat_menu_button.await_args_list == first_run


def test_rollout_access_requires_enabled_flag_and_allowlist_membership() -> None:
    restricted = make_rollout(allowed_telegram_ids=frozenset({111}))
    global_rollout = make_rollout()
    disabled = make_rollout(enabled=False)

    assert restricted.is_available_to(111) is True
    assert restricted.is_available_to(222) is False
    assert global_rollout.is_available_to(222) is True
    assert disabled.is_available_to(111) is False
