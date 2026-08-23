import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiogram import Router
from aiogram.types import Update

from app.bot.middlewares.rate_limit import (
    RATE_LIMIT_TEXT,
    RateLimitMiddleware,
    resolve_rate_limit_scopes,
)
from app.bot.states.dishes import DishSearchStates
from app.bot.states.ingredients import IngredientSearchStates
from app.bot.states.weights import WeightChartStates
from app.config import Settings
from app.main import create_dispatcher
from app.services.rate_limit import RateLimitRule, RateLimitScope, RateLimitService

DEFAULT_MESSAGE_RULE = RateLimitRule(10, 10)
DEFAULT_CALLBACK_RULE = RateLimitRule(20, 10)
DEFAULT_SEARCH_RULE = RateLimitRule(5, 10)
DEFAULT_WEIGHT_CHART_RULE = RateLimitRule(3, 60)
DEFAULT_SHARE_CREATE_RULE = RateLimitRule(10, 60)
DEFAULT_SHARE_OPEN_RULE = RateLimitRule(20, 60)
DEFAULT_SHARE_IMPORT_RULE = RateLimitRule(10, 60)
DEFAULT_SHARE_ROTATE_RULE = RateLimitRule(5, 60)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_service(
    clock: FakeClock,
    *,
    messages: RateLimitRule = DEFAULT_MESSAGE_RULE,
    callbacks: RateLimitRule = DEFAULT_CALLBACK_RULE,
    search: RateLimitRule = DEFAULT_SEARCH_RULE,
    weight_chart: RateLimitRule = DEFAULT_WEIGHT_CHART_RULE,
    share_create: RateLimitRule = DEFAULT_SHARE_CREATE_RULE,
    share_open: RateLimitRule = DEFAULT_SHARE_OPEN_RULE,
    share_import: RateLimitRule = DEFAULT_SHARE_IMPORT_RULE,
    share_rotate: RateLimitRule = DEFAULT_SHARE_ROTATE_RULE,
    notice_cooldown: int = 5,
) -> RateLimitService:
    return RateLimitService(
        {
            RateLimitScope.MESSAGES: messages,
            RateLimitScope.CALLBACKS: callbacks,
            RateLimitScope.SEARCH: search,
            RateLimitScope.WEIGHT_CHART: weight_chart,
            RateLimitScope.SHARE_CREATE: share_create,
            RateLimitScope.SHARE_OPEN: share_open,
            RateLimitScope.SHARE_IMPORT: share_import,
            RateLimitScope.SHARE_ROTATE: share_rotate,
        },
        notice_cooldown_seconds=notice_cooldown,
        clock=clock,
    )


def make_message_update(update_id: int = 1) -> tuple[Update, Mock]:
    message = Mock(answer=AsyncMock(), text=None)
    update = Update.model_construct(
        update_id=update_id,
        message=message,
        callback_query=None,
    )
    return update, message


def make_callback_update(
    data: str = "menu:open",
    update_id: int = 1,
) -> tuple[Update, Mock]:
    callback = Mock(data=data, answer=AsyncMock())
    update = Update.model_construct(
        update_id=update_id,
        message=None,
        callback_query=callback,
    )
    return update, callback


def test_sliding_window_blocks_and_recovers() -> None:
    clock = FakeClock()
    service = make_service(clock, messages=RateLimitRule(2, 10))

    assert service.check(1, RateLimitScope.MESSAGES).allowed
    clock.advance(1)
    assert service.check(1, RateLimitScope.MESSAGES).allowed
    blocked = service.check(1, RateLimitScope.MESSAGES)

    assert not blocked.allowed
    assert blocked.retry_after_seconds == 9

    clock.advance(9)
    assert service.check(1, RateLimitScope.MESSAGES).allowed


def test_users_have_independent_buckets() -> None:
    clock = FakeClock()
    service = make_service(clock, messages=RateLimitRule(1, 10))

    assert service.check(1, RateLimitScope.MESSAGES).allowed
    assert not service.check(1, RateLimitScope.MESSAGES).allowed
    assert service.check(2, RateLimitScope.MESSAGES).allowed


def test_heavy_scopes_are_independent() -> None:
    clock = FakeClock()
    service = make_service(
        clock,
        search=RateLimitRule(1, 10),
        weight_chart=RateLimitRule(1, 60),
    )

    assert service.check(1, RateLimitScope.SEARCH).allowed
    assert not service.check(1, RateLimitScope.SEARCH).allowed
    assert service.check(1, RateLimitScope.WEIGHT_CHART).allowed
    assert not service.check(1, RateLimitScope.WEIGHT_CHART).allowed
    assert service.check(1, RateLimitScope.MESSAGES).allowed


def test_notice_cooldown_prevents_response_spam() -> None:
    clock = FakeClock()
    service = make_service(clock, notice_cooldown=5)

    assert service.should_send_notice(1)
    assert not service.should_send_notice(1)
    clock.advance(5)
    assert service.should_send_notice(1)
    assert service.should_send_notice(2)


async def test_message_middleware_rejects_without_repeating_notice() -> None:
    clock = FakeClock()
    service = make_service(clock, messages=RateLimitRule(1, 10))
    middleware = RateLimitMiddleware(service)
    handler = AsyncMock(return_value="handled")
    update, message = make_message_update()
    data = {"event_from_user": SimpleNamespace(id=42), "raw_state": None}

    assert await middleware(handler, update, data) == "handled"
    assert await middleware(handler, update, data) is None
    assert await middleware(handler, update, data) is None

    handler.assert_awaited_once()
    message.answer.assert_awaited_once_with(RATE_LIMIT_TEXT)


async def test_callback_middleware_always_stops_spinner() -> None:
    clock = FakeClock()
    service = make_service(clock, callbacks=RateLimitRule(1, 10))
    middleware = RateLimitMiddleware(service)
    handler = AsyncMock(return_value="handled")
    update, callback = make_callback_update()
    data = {"event_from_user": SimpleNamespace(id=42), "raw_state": None}

    assert await middleware(handler, update, data) == "handled"
    assert await middleware(handler, update, data) is None
    assert await middleware(handler, update, data) is None

    assert callback.answer.await_count == 2
    assert callback.answer.await_args_list[0].args == (RATE_LIMIT_TEXT,)
    assert callback.answer.await_args_list[1].args == (None,)


async def test_spam_burst_is_limited_without_affecting_another_user() -> None:
    clock = FakeClock()
    service = make_service(clock)
    middleware = RateLimitMiddleware(service)
    message_handler = AsyncMock(return_value="message-handled")
    callback_handler = AsyncMock(return_value="callback-handled")
    message_update, message = make_message_update()
    callback_update, callback = make_callback_update()
    spammer = {"event_from_user": SimpleNamespace(id=42), "raw_state": None}
    other_user = {"event_from_user": SimpleNamespace(id=43), "raw_state": None}

    message_results = await asyncio.gather(
        *(middleware(message_handler, message_update, spammer) for _ in range(30))
    )
    callback_results = await asyncio.gather(
        *(middleware(callback_handler, callback_update, spammer) for _ in range(30))
    )

    assert message_results.count("message-handled") == 10
    assert callback_results.count("callback-handled") == 20
    assert message.answer.await_count == 1
    assert callback.answer.await_count == 10
    assert (
        await middleware(message_handler, message_update, other_user)
        == "message-handled"
    )
    assert (
        await middleware(callback_handler, callback_update, other_user)
        == "callback-handled"
    )


def test_search_messages_receive_search_scope() -> None:
    update, _ = make_message_update()

    ingredient_scopes = resolve_rate_limit_scopes(
        update,
        {"raw_state": IngredientSearchStates.wait_query.state},
    )
    dish_scopes = resolve_rate_limit_scopes(
        update,
        {"raw_state": DishSearchStates.wait_query.state},
    )

    expected = (RateLimitScope.MESSAGES, RateLimitScope.SEARCH)
    assert ingredient_scopes == expected
    assert dish_scopes == expected


def test_weight_chart_callbacks_receive_heavy_scope() -> None:
    for callback_data in ("weight:chart", "weight_chart:30", "wch:365"):
        update, _ = make_callback_update(callback_data)

        assert resolve_rate_limit_scopes(update, {}) == (
            RateLimitScope.CALLBACKS,
            RateLimitScope.WEIGHT_CHART,
        )


def test_custom_weight_chart_render_message_receives_heavy_scope() -> None:
    update, _ = make_message_update()

    assert resolve_rate_limit_scopes(
        update,
        {"raw_state": WeightChartStates.wait_date_to.state},
    ) == (RateLimitScope.MESSAGES, RateLimitScope.WEIGHT_CHART)


def test_sharing_operations_receive_dedicated_user_scopes() -> None:
    message_update, _ = make_message_update()
    message_update.message.text = (  # type: ignore[union-attr]
        "/start sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    assert resolve_rate_limit_scopes(message_update, {}) == (
        RateLimitScope.MESSAGES,
        RateLimitScope.SHARE_OPEN,
    )

    cases = {
        "ingredient:share:55:1": RateLimitScope.SHARE_CREATE,
        "shsel:create": RateLimitScope.SHARE_CREATE,
        "confirm:share_import:action123": RateLimitScope.SHARE_IMPORT,
        "confirm:share_rotate_manage:action123": RateLimitScope.SHARE_ROTATE,
    }
    for callback_data, expected_scope in cases.items():
        callback_update, _ = make_callback_update(callback_data)
        assert resolve_rate_limit_scopes(callback_update, {}) == (
            RateLimitScope.CALLBACKS,
            expected_scope,
        )


def test_share_limits_are_per_user_not_per_token() -> None:
    clock = FakeClock()
    service = make_service(clock, share_open=RateLimitRule(1, 60))

    assert service.check(1, RateLimitScope.SHARE_OPEN).allowed
    assert not service.check(1, RateLimitScope.SHARE_OPEN).allowed
    assert service.check(2, RateLimitScope.SHARE_OPEN).allowed


async def test_rate_limit_runs_before_user_database_middleware(monkeypatch) -> None:
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/database",
        _env_file=None,
    )
    monkeypatch.setattr("app.main.build_root_router", lambda: Router())
    dispatcher = create_dispatcher(settings)

    try:
        names = [
            type(middleware).__name__
            for middleware in dispatcher.update.outer_middleware
        ]
        assert names.index("CorrelationIdMiddleware") < names.index(
            "RateLimitMiddleware"
        )
        assert names.index("RateLimitMiddleware") < names.index("UserMiddleware")
        assert names.index("RateLimitMiddleware") < names.index("ActionLockMiddleware")
        assert names.index("ActionLockMiddleware") < names.index("UserMiddleware")
    finally:
        await dispatcher["database_engine"].dispose()
