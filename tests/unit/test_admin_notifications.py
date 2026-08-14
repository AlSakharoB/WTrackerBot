from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.types import Message, User
from pydantic import ValidationError as PydanticValidationError

from app.bot.handlers.common import global_error_handler
from app.config import Settings
from app.exceptions import NotFoundError, ValidationError
from app.services.admin_notifications import (
    AdminNotificationService,
    build_error_fingerprint,
)

VALID_SETTINGS = {
    "bot_token": "test-token",
    "database_url": "postgresql+asyncpg://user:pass@localhost/database",
}


class FakeClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make_error(message: str = "controlled failure") -> RuntimeError:
    try:
        raise RuntimeError(message)
    except RuntimeError as error:
        return error


def make_service(
    *,
    admin_ids: set[int] | None = None,
    cooldown: int = 300,
    max_per_minute: int = 10,
    clock: FakeClock | None = None,
) -> tuple[AdminNotificationService, AsyncMock]:
    send_message = AsyncMock()
    bot = Mock(send_message=send_message)
    service = AdminNotificationService(
        bot,
        admin_ids if admin_ids is not None else {111},
        cooldown_seconds=cooldown,
        max_per_minute=max_per_minute,
        monotonic_clock=clock or FakeClock(),
        utcnow=lambda: datetime(2026, 8, 14, 10, 22, tzinfo=UTC),
    )
    return service, send_message


def test_settings_parse_admin_ids_and_error_limits() -> None:
    settings = Settings(
        **VALID_SETTINGS,
        _env_file=None,
        admin_telegram_ids="123, 456,123",
        admin_error_cooldown_seconds=60,
        admin_error_max_per_minute=5,
    )

    assert settings.admin_telegram_ids == {123, 456}
    assert settings.admin_error_cooldown_seconds == 60
    assert settings.admin_error_max_per_minute == 5


def test_settings_allow_empty_admin_ids() -> None:
    settings = Settings(
        **VALID_SETTINGS,
        admin_telegram_ids="",
        _env_file=None,
    )

    assert settings.admin_telegram_ids == set()


@pytest.mark.parametrize("value", ["abc", "123,invalid", "-1", "0"])
def test_settings_reject_invalid_admin_ids(value: str) -> None:
    with pytest.raises(PydanticValidationError, match="ADMIN_TELEGRAM_IDS"):
        Settings(**VALID_SETTINGS, admin_telegram_ids=value, _env_file=None)


async def test_critical_error_is_sent_to_every_admin_without_secrets() -> None:
    service, send_message = make_service(admin_ids={222, 111})
    error = make_error(
        "BOT_TOKEN=secret DATABASE_URL=postgresql+asyncpg://user:pass@db/name"
    )

    await service.notify_error(
        error,
        correlation_id="tg-987",
        operation="diary.add_food",
        user_id=42,
    )

    assert send_message.await_count == 2
    assert [call.kwargs["chat_id"] for call in send_message.await_args_list] == [
        111,
        222,
    ]
    text = send_message.await_args_list[0].kwargs["text"]
    assert "Тип: RuntimeError" in text
    assert "Операция: diary.add_food" in text
    assert "Correlation ID: tg-987" in text
    assert "User ID: 42" in text
    assert "14.08.2026 10:22 UTC" in text
    assert "Fingerprint:" in text
    assert "secret" not in text
    assert "DATABASE_URL" not in text
    assert "Traceback" not in text
    assert "controlled failure" not in text


def test_fingerprint_is_stable_and_operation_specific() -> None:
    error = make_error()

    first = build_error_fingerprint(error, "diary.add_food")
    second = build_error_fingerprint(error, "diary.add_food")
    another_operation = build_error_fingerprint(error, "weight.add")

    assert first == second
    assert first != another_operation
    assert len(first) == 16


async def test_duplicate_errors_are_aggregated_during_cooldown() -> None:
    clock = FakeClock()
    service, send_message = make_service(clock=clock)
    error = make_error()

    await service.notify_error(error, "tg-1", "diary.add_food", 42)
    await service.notify_error(error, "tg-2", "diary.add_food", 42)

    assert send_message.await_count == 1
    assert service.stats.suppressed_notifications == 1

    clock.advance(301)
    await service.notify_error(error, "tg-3", "diary.add_food", 42)

    assert send_message.await_count == 2
    assert "Подавлено повторов: 1" in send_message.await_args.kwargs["text"]


async def test_notification_storm_is_suppressed() -> None:
    service, send_message = make_service(max_per_minute=2)
    error = make_error()

    await service.notify_error(error, None, "operation.one", None)
    await service.notify_error(error, None, "operation.two", None)
    await service.notify_error(error, None, "operation.three", None)

    assert send_message.await_count == 2
    assert service.stats.total_errors == 3
    assert service.stats.suppressed_notifications == 1


async def test_validation_and_not_found_errors_are_not_alerted() -> None:
    service, send_message = make_service()

    await service.notify_error(ValidationError("invalid"), None, None, None)
    await service.notify_error(NotFoundError("missing"), None, None, None)

    send_message.assert_not_awaited()
    assert service.stats.total_errors == 0


async def test_empty_admin_list_keeps_runtime_stats_without_sending() -> None:
    service, send_message = make_service(admin_ids=set())

    await service.notify_error(make_error(), None, "worker.run", None)

    send_message.assert_not_awaited()
    assert service.stats.total_errors == 1
    assert service.stats.last_error_at == datetime(2026, 8, 14, 10, 22, tzinfo=UTC)
    assert service.stats.last_fingerprint is not None


async def test_send_failure_does_not_raise_or_block_other_admins() -> None:
    service, send_message = make_service(admin_ids={111, 222})
    send_message.side_effect = [RuntimeError("telegram failure"), None]

    await service.notify_error(make_error(), None, "worker.run", None)

    assert send_message.await_count == 2


async def test_global_error_handler_notifies_service() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.from_user = User(id=77, is_bot=False, first_name="Test")
    notification_service = SimpleNamespace(notify_error=AsyncMock())
    error = make_error()
    event = SimpleNamespace(
        exception=error,
        update=SimpleNamespace(
            update_id=654,
            message=message,
            callback_query=None,
        ),
    )

    handled = await global_error_handler(  # type: ignore[arg-type]
        event,
        admin_notification_service=notification_service,
    )

    assert handled is True
    notification_service.notify_error.assert_awaited_once_with(
        error,
        correlation_id="tg-654",
        operation="telegram.message",
        user_id=77,
    )


async def test_global_domain_error_does_not_notify_service() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    notification_service = SimpleNamespace(notify_error=AsyncMock())
    event = SimpleNamespace(
        exception=ValidationError("Некорректное значение."),
        update=SimpleNamespace(
            update_id=123,
            message=message,
            callback_query=None,
        ),
    )

    await global_error_handler(  # type: ignore[arg-type]
        event,
        admin_notification_service=notification_service,
    )

    notification_service.notify_error.assert_not_awaited()


def test_migrate_service_notifies_about_failed_migration() -> None:
    project_root = Path(__file__).parents[2]
    entrypoint = project_root.joinpath("docker/entrypoint.sh").read_text()
    migrate_script = project_root.joinpath("scripts/migrate.py").read_text()

    assert "alembic upgrade head" not in entrypoint
    assert "notify_migration_failure" in migrate_script
    assert "sys.exit(1)" in migrate_script
