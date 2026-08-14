from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramNetworkError

from app.config import Settings
from app.core.health import (
    DatabaseRevisionMismatchError,
    DatabaseRevisionState,
    DatabaseRevisionStatus,
)
from app.core.lifecycle import LifecycleManager
from app.main import run_bot


class FakeDispatcher:
    def __init__(self, engine: Mock) -> None:
        self.engine = engine
        self.workflow_data: dict[str, object] = {
            "lifecycle_manager": LifecycleManager(drain_timeout_seconds=1),
            "database_session_factory": Mock(),
        }
        self.start_polling = AsyncMock()

    def __getitem__(self, key: str) -> object:
        if key == "database_engine":
            return self.engine
        return self.workflow_data[key]

    def __setitem__(self, key: str, value: object) -> None:
        self.workflow_data[key] = value


class FakeReminderScheduler:
    def __init__(self) -> None:
        self.start = AsyncMock()
        self.shutdown = AsyncMock()
        self.running = True
        self.job_count = 0
        self.last_heartbeat = None
        self.next_job_time = None


def patch_reminder_scheduler(monkeypatch) -> FakeReminderScheduler:
    scheduler = FakeReminderScheduler()
    monkeypatch.setattr("app.main.ReminderScheduler", Mock(return_value=scheduler))
    return scheduler


def patch_revision_guard(monkeypatch) -> AsyncMock:
    revision = DatabaseRevisionState(
        current=("head",),
        expected=("head",),
        status=DatabaseRevisionStatus.UP_TO_DATE,
    )
    guard = AsyncMock(return_value=revision)
    monkeypatch.setattr("app.main.ensure_database_revision_current", guard)
    return guard


async def test_command_registration_failure_does_not_block_polling(
    monkeypatch,
) -> None:
    engine = Mock()
    engine.dispose = AsyncMock()
    dispatcher = FakeDispatcher(engine)
    session = Mock()
    session.close = AsyncMock()
    bot = Mock(session=session)
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,
    )
    check_database = AsyncMock()
    register_commands = AsyncMock(
        side_effect=TelegramNetworkError(method=Mock(), message="network")
    )

    monkeypatch.setattr("app.main.create_dispatcher", lambda _: dispatcher)
    monkeypatch.setattr("app.main.Bot", lambda **_: bot)
    monkeypatch.setattr("app.main.check_database_connection", check_database)
    revision_guard = patch_revision_guard(monkeypatch)
    monkeypatch.setattr("app.main.set_bot_commands", register_commands)
    scheduler = patch_reminder_scheduler(monkeypatch)

    await run_bot(settings)

    check_database.assert_awaited_once_with(engine)
    revision_guard.assert_awaited_once_with(engine)
    dispatcher.start_polling.assert_awaited_once_with(
        bot,
        close_bot_session=False,
        handle_signals=True,
    )
    session.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    scheduler.start.assert_awaited_once()
    scheduler.shutdown.assert_awaited_once()


async def test_database_startup_failure_notifies_admin(monkeypatch) -> None:
    engine = Mock(dispose=AsyncMock())
    dispatcher = FakeDispatcher(engine)
    bot = Mock(session=Mock(close=AsyncMock()), send_message=AsyncMock())
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        admin_telegram_ids={111},
        _env_file=None,
    )
    database_error = OSError("database unavailable")

    monkeypatch.setattr("app.main.create_dispatcher", lambda _: dispatcher)
    monkeypatch.setattr("app.main.Bot", lambda **_: bot)
    monkeypatch.setattr(
        "app.main.check_database_connection",
        AsyncMock(side_effect=database_error),
    )

    with pytest.raises(OSError, match="database unavailable"):
        await run_bot(settings)

    bot.send_message.assert_awaited_once()
    notification = bot.send_message.await_args.kwargs["text"]
    assert "Тип: OSError" in notification
    assert "Операция: database.connect" in notification
    bot.session.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_unexpected_polling_failure_notifies_admin(monkeypatch) -> None:
    engine = Mock(dispose=AsyncMock())
    dispatcher = FakeDispatcher(engine)
    polling_error = RuntimeError("polling failed")
    dispatcher.start_polling.side_effect = polling_error
    bot = Mock(session=Mock(close=AsyncMock()), send_message=AsyncMock())
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        admin_telegram_ids={111},
        _env_file=None,
    )

    monkeypatch.setattr("app.main.create_dispatcher", lambda _: dispatcher)
    monkeypatch.setattr("app.main.Bot", lambda **_: bot)
    monkeypatch.setattr("app.main.check_database_connection", AsyncMock())
    patch_revision_guard(monkeypatch)
    monkeypatch.setattr("app.main.set_bot_commands", AsyncMock())
    patch_reminder_scheduler(monkeypatch)

    with pytest.raises(RuntimeError, match="polling failed"):
        await run_bot(settings)

    bot.send_message.assert_awaited_once()
    notification = bot.send_message.await_args.kwargs["text"]
    assert "Тип: RuntimeError" in notification
    assert "Операция: telegram.polling" in notification
    bot.session.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_http_client_close_failure_does_not_skip_database_disposal(
    monkeypatch,
) -> None:
    engine = Mock(dispose=AsyncMock())
    dispatcher = FakeDispatcher(engine)
    bot = Mock(
        session=Mock(close=AsyncMock(side_effect=OSError("close failed"))),
        send_message=AsyncMock(),
    )
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        _env_file=None,
    )

    monkeypatch.setattr("app.main.create_dispatcher", lambda _: dispatcher)
    monkeypatch.setattr("app.main.Bot", lambda **_: bot)
    monkeypatch.setattr("app.main.check_database_connection", AsyncMock())
    patch_revision_guard(monkeypatch)
    monkeypatch.setattr("app.main.set_bot_commands", AsyncMock())
    patch_reminder_scheduler(monkeypatch)

    await run_bot(settings)

    bot.session.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()


async def test_revision_mismatch_blocks_polling_and_notifies_admin(monkeypatch) -> None:
    engine = Mock(dispose=AsyncMock())
    dispatcher = FakeDispatcher(engine)
    bot = Mock(session=Mock(close=AsyncMock()), send_message=AsyncMock())
    settings = Settings(
        bot_token="test-token",
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        admin_telegram_ids={111},
        _env_file=None,
    )
    state = DatabaseRevisionState(
        current=("old",),
        expected=("head",),
        status=DatabaseRevisionStatus.BEHIND,
    )
    mismatch = DatabaseRevisionMismatchError(state)

    monkeypatch.setattr("app.main.create_dispatcher", lambda _: dispatcher)
    monkeypatch.setattr("app.main.Bot", lambda **_: bot)
    monkeypatch.setattr("app.main.check_database_connection", AsyncMock())
    monkeypatch.setattr(
        "app.main.ensure_database_revision_current",
        AsyncMock(side_effect=mismatch),
    )
    scheduler = patch_reminder_scheduler(monkeypatch)

    with pytest.raises(DatabaseRevisionMismatchError, match="behind"):
        await run_bot(settings)

    dispatcher.start_polling.assert_not_awaited()
    scheduler.start.assert_not_awaited()
    bot.send_message.assert_awaited_once()
    notification = bot.send_message.await_args.kwargs["text"]
    assert "DatabaseRevisionMismatchError" in notification
    assert "database.revision_guard" in notification
