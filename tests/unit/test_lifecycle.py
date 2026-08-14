import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from aiogram import Router

from app.bot.middlewares.lifecycle import LifecycleMiddleware
from app.config import Settings
from app.core.lifecycle import LifecycleManager
from app.main import create_dispatcher


async def test_shutdown_waits_for_active_update() -> None:
    lifecycle = LifecycleManager(drain_timeout_seconds=1)
    middleware = LifecycleMiddleware(lifecycle)
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_event: object, _data: dict[str, object]) -> str:
        started.set()
        await release.wait()
        return "completed"

    update_task = asyncio.create_task(middleware(handler, object(), {}))
    await started.wait()
    shutdown_task = asyncio.create_task(lifecycle.shutdown())
    await asyncio.sleep(0)

    assert not lifecycle.accepting_updates
    assert lifecycle.active_update_count == 1
    assert not shutdown_task.done()

    release.set()
    assert await update_task == "completed"
    await shutdown_task
    assert lifecycle.active_update_count == 0


async def test_shutdown_cancels_handler_after_drain_timeout() -> None:
    lifecycle = LifecycleManager(drain_timeout_seconds=0.01)  # type: ignore[arg-type]
    middleware = LifecycleMiddleware(lifecycle)
    started = asyncio.Event()

    async def handler(_event: object, _data: dict[str, object]) -> None:
        started.set()
        await asyncio.Event().wait()

    update_task = asyncio.create_task(middleware(handler, object(), {}))
    await started.wait()

    await lifecycle.shutdown()

    assert update_task.cancelled()
    assert lifecycle.active_update_count == 0


async def test_updates_are_rejected_after_shutdown_starts() -> None:
    lifecycle = LifecycleManager(drain_timeout_seconds=1)
    middleware = LifecycleMiddleware(lifecycle)
    handler = AsyncMock()
    await lifecycle.shutdown()

    result = await middleware(handler, object(), {})

    assert result is None
    handler.assert_not_awaited()


async def test_shutdown_stops_components_then_background_tasks() -> None:
    lifecycle = LifecycleManager(drain_timeout_seconds=1)
    events: list[str] = []
    background_started = asyncio.Event()

    async def stop_scheduler() -> None:
        events.append("scheduler")

    async def background_worker() -> None:
        background_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            events.append("background")

    lifecycle.register_shutdown_callback("scheduler", stop_scheduler)
    task = asyncio.create_task(background_worker())
    lifecycle.register_background_task(task)
    await background_started.wait()

    await lifecycle.shutdown()

    assert events == ["scheduler", "background"]
    assert task.cancelled()
    assert lifecycle.background_task_count == 0


async def test_shutdown_is_idempotent() -> None:
    lifecycle = LifecycleManager(drain_timeout_seconds=1)
    callback = AsyncMock()
    lifecycle.register_shutdown_callback("component", callback)

    await lifecycle.shutdown()
    await lifecycle.shutdown()

    callback.assert_awaited_once()


async def test_dispatcher_orders_lifecycle_before_errors_and_fsm(monkeypatch) -> None:
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/database",
        _env_file=None,
    )
    monkeypatch.setattr("app.main.build_root_router", lambda: Router())
    dispatcher = create_dispatcher(settings)

    try:
        middleware_names = [
            type(middleware).__name__
            for middleware in dispatcher.update.outer_middleware
        ]
        shutdown_names = [
            handler.callback.__qualname__ for handler in dispatcher.shutdown.handlers
        ]

        assert middleware_names[:2] == ["LifecycleMiddleware", "ErrorsMiddleware"]
        assert shutdown_names[:2] == [
            "LifecycleManager.shutdown",
            "FSMContextMiddleware.close",
        ]
    finally:
        await dispatcher["database_engine"].dispose()


def test_compose_grants_shutdown_cleanup_time() -> None:
    compose = Path(__file__).parents[2].joinpath("docker-compose.yml").read_text()

    assert "stop_grace_period: 30s" in compose
