import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.types import Update

from app.bot.actions import STALE_ACTION_TEXT, confirmation_data
from app.bot.keyboards.actions import DIARY_SAVE_ACTION, ConfirmActionCallback
from app.bot.middlewares.action_lock import (
    ACTION_IN_PROGRESS_TEXT,
    ActionLockMiddleware,
    resolve_action_lock_key,
)
from app.services.action_lock import ActionLockService, action_token_matches


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_callback_update(callback_data: str) -> tuple[Update, Mock]:
    callback = Mock(data=callback_data, answer=AsyncMock())
    update = Update.model_construct(
        update_id=1,
        message=None,
        callback_query=callback,
    )
    return update, callback


def test_action_lock_expires_after_ttl() -> None:
    clock = FakeClock()
    service = ActionLockService(20, clock=clock)

    assert service.acquire("42:create:item") is not None
    assert service.acquire("42:create:item") is None
    clock.advance(20)
    assert service.acquire("42:create:item") is not None


def test_action_lock_release_only_accepts_current_lease() -> None:
    clock = FakeClock()
    service = ActionLockService(20, clock=clock)
    first = service.acquire("42:create:item")
    assert first is not None
    clock.advance(20)
    second = service.acquire("42:create:item")
    assert second is not None

    service.release(first)

    assert service.acquire("42:create:item") is None


@pytest.mark.parametrize("callback_count", [2, 5, 30])
async def test_concurrent_callbacks_run_exactly_one_operation(
    callback_count: int,
) -> None:
    callback_data = ConfirmActionCallback(
        action=DIARY_SAVE_ACTION,
        token="fsm-abc123",
    ).pack()
    update, callback = make_callback_update(callback_data)
    middleware = ActionLockMiddleware(ActionLockService(20))
    started = asyncio.Event()
    finish = asyncio.Event()
    operation_count = 0

    async def handler(_event: object, _data: dict[str, object]) -> str:
        nonlocal operation_count
        operation_count += 1
        started.set()
        await finish.wait()
        return "created"

    tasks = [
        asyncio.create_task(
            middleware(
                handler,
                update,
                {"event_from_user": SimpleNamespace(id=42)},
            )
        )
        for _ in range(callback_count)
    ]
    await started.wait()
    await asyncio.sleep(0)
    finish.set()
    results = await asyncio.gather(*tasks)

    assert operation_count == 1
    assert results.count("created") == 1
    assert callback.answer.await_count == callback_count - 1
    assert all(
        call.args == (ACTION_IN_PROGRESS_TEXT,)
        for call in callback.answer.await_args_list
    )


async def test_exception_releases_action_lock() -> None:
    callback_data = ConfirmActionCallback(
        action=DIARY_SAVE_ACTION,
        token="fsm-abc123",
    ).pack()
    update, _ = make_callback_update(callback_data)
    middleware = ActionLockMiddleware(ActionLockService(20))
    data = {"event_from_user": SimpleNamespace(id=42)}

    async def failing_handler(_event: object, _data: dict[str, object]) -> None:
        raise RuntimeError("database unavailable")

    with pytest.raises(RuntimeError, match="database unavailable"):
        await middleware(failing_handler, update, data)

    successful_handler = AsyncMock(return_value="created")
    assert await middleware(successful_handler, update, data) == "created"
    successful_handler.assert_awaited_once()


def test_lock_key_contains_user_action_and_token() -> None:
    callback_data = ConfirmActionCallback(
        action=DIARY_SAVE_ACTION,
        token="fsm-abc123",
    ).pack()
    update, _ = make_callback_update(callback_data)

    assert resolve_action_lock_key(update, 42) == ("42:diary_save:fsm-abc123")


def test_delete_confirmation_is_also_locked() -> None:
    update, _ = make_callback_update("ingredient:delete_confirm:17:1")

    assert resolve_action_lock_key(update, 42) == ("42:ingredient:delete_confirm:17:1")


def test_action_token_comparison_rejects_stale_values() -> None:
    assert action_token_matches("current-token", "current-token")
    assert not action_token_matches("current-token", "stale-token")
    assert not action_token_matches(None, "current-token")


async def test_stale_confirmation_token_stops_handler_data_flow() -> None:
    callback = Mock(answer=AsyncMock())
    state = Mock(get_data=AsyncMock(return_value={"action_token": "current-token"}))

    data = await confirmation_data(callback, state, "stale-token")

    assert data is None
    callback.answer.assert_awaited_once_with(STALE_ACTION_TEXT, show_alert=True)
