from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import (
    ACCESS_DENIED_TEXT,
    ADMIN_MENU_TEXT,
    admin_callback,
    admin_command,
)
from app.bot.keyboards.admin import AdminAction, AdminCallback
from app.core.health import HealthCheckResult, HealthReport, HealthStatus
from app.repositories.admin import (
    AdminDatabaseInfo,
    AdminEntityStats,
    AdminRepository,
    AdminUserStats,
)
from app.services.admin_notifications import ErrorRuntimeStats


def make_message(user_id: int) -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.from_user = User(id=user_id, is_bot=False, first_name="Admin")
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    message.delete = AsyncMock()
    return message


def make_callback(user_id: int) -> AsyncMock:
    callback = AsyncMock(spec=CallbackQuery)
    callback.from_user = User(id=user_id, is_bot=False, first_name="Admin")
    callback.answer = AsyncMock()
    callback.message = make_message(user_id)
    return callback


def make_health_service() -> Mock:
    started_at = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)
    report = HealthReport(
        status=HealthStatus.OK,
        checks=(
            HealthCheckResult("bot", HealthStatus.OK, "fresh"),
            HealthCheckResult("database", HealthStatus.OK, "available", 8.0),
            HealthCheckResult("telegram", HealthStatus.OK, "available", 12.0),
            HealthCheckResult("scheduler", HealthStatus.OK, "running"),
            HealthCheckResult(
                "database_revision",
                HealthStatus.OK,
                "up_to_date",
            ),
        ),
        started_at=started_at,
        generated_at=started_at,
    )
    revision = HealthCheckResult(
        "database_revision",
        HealthStatus.OK,
        "up_to_date",
        details={"current": "revision-1", "expected": "revision-1"},
    )
    return Mock(
        get_full_health=AsyncMock(return_value=report),
        check_database_revision=AsyncMock(return_value=revision),
        started_at=started_at,
        uptime_seconds=3720,
    )


def make_notification_service() -> Mock:
    return Mock(
        stats=ErrorRuntimeStats(
            total_errors=3,
            last_error_at=datetime(2026, 8, 14, 10, 30, tzinfo=UTC),
            last_fingerprint="abc123",
            suppressed_notifications=2,
        )
    )


async def call_admin_callback(
    callback: AsyncMock,
    action: AdminAction,
    *,
    health_service: Mock | None = None,
    notification_service: Mock | None = None,
    db_session: Mock | None = None,
    admin_ids: set[int] | None = None,
) -> None:
    await admin_callback(
        callback,
        AdminCallback(action=action),
        admin_ids if admin_ids is not None else {111},
        db_session or Mock(spec=AsyncSession),
        health_service or make_health_service(),
        notification_service or make_notification_service(),
        "production",
        "1.2.3",
        "abc123def456",
    )


async def test_admin_command_allows_configured_admin() -> None:
    message = make_message(111)
    state = AsyncMock(spec=FSMContext)

    await admin_command(message, state, {111, 222})

    state.clear.assert_awaited_once()
    assert message.answer.await_args.args[0] == ADMIN_MENU_TEXT
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 7


async def test_admin_command_denies_regular_user() -> None:
    message = make_message(999)
    state = AsyncMock(spec=FSMContext)

    await admin_command(message, state, {111})

    message.answer.assert_awaited_once_with(ACCESS_DENIED_TEXT)
    state.clear.assert_not_awaited()


async def test_admin_callback_rechecks_access() -> None:
    callback = make_callback(999)
    health_service = make_health_service()

    await call_admin_callback(
        callback,
        AdminAction.HEALTH,
        health_service=health_service,
        admin_ids={111},
    )

    callback.answer.assert_awaited_once_with(ACCESS_DENIED_TEXT, show_alert=True)
    callback.message.edit_text.assert_not_awaited()
    health_service.get_full_health.assert_not_awaited()


async def test_admin_health_screen_uses_health_service() -> None:
    callback = make_callback(111)
    health_service = make_health_service()

    await call_admin_callback(
        callback,
        AdminAction.HEALTH,
        health_service=health_service,
    )

    health_service.get_full_health.assert_awaited_once()
    text = callback.message.edit_text.await_args.args[0]
    assert "🟢 HEALTHY" in text
    assert "Bot: OK" in text
    assert "Database: OK" in text
    assert "Telegram: OK" in text
    assert "Scheduler: OK" in text
    assert "DB revision: OK" in text


async def test_admin_user_stats_screen(monkeypatch) -> None:
    callback = make_callback(111)
    repository = Mock(get_user_stats=AsyncMock(return_value=AdminUserStats(100, 4, 20)))
    monkeypatch.setattr(
        "app.bot.handlers.admin.AdminRepository",
        lambda _: repository,
    )

    await call_admin_callback(callback, AdminAction.USERS)

    text = callback.message.edit_text.await_args.args[0]
    assert "Всего пользователей: 100" in text
    assert "Новых сегодня: 4" in text
    assert "Новых за 7 дней: 20" in text
    assert "username" not in text.lower()


async def test_admin_entity_stats_screen(monkeypatch) -> None:
    callback = make_callback(111)
    repository = Mock(
        get_entity_stats=AsyncMock(return_value=AdminEntityStats(10, 20, 30, 40, 2))
    )
    monkeypatch.setattr(
        "app.bot.handlers.admin.AdminRepository",
        lambda _: repository,
    )

    await call_admin_callback(callback, AdminAction.STATS)

    text = callback.message.edit_text.await_args.args[0]
    assert "Ингредиенты: 10" in text
    assert "Блюда: 20" in text
    assert "Записи питания: 30" in text
    assert "Записи веса: 40" in text
    assert "Активные цели веса: 2" in text


async def test_admin_database_screen(monkeypatch) -> None:
    callback = make_callback(111)
    repository = Mock(
        get_database_info=AsyncMock(return_value=AdminDatabaseInfo("16.4", "12 MB"))
    )
    monkeypatch.setattr(
        "app.bot.handlers.admin.AdminRepository",
        lambda _: repository,
    )

    await call_admin_callback(callback, AdminAction.DATABASE)

    text = callback.message.edit_text.await_args.args[0]
    assert "PostgreSQL: 16.4" in text
    assert "Размер: 12 MB" in text
    assert "Current revision: revision-1" in text
    assert "Expected head: revision-1" in text
    assert "Статус: UP_TO_DATE" in text


async def test_admin_version_screen_does_not_expose_secrets() -> None:
    callback = make_callback(111)

    await call_admin_callback(callback, AdminAction.VERSION)

    text = callback.message.edit_text.await_args.args[0]
    assert "App version: 1.2.3" in text
    assert "Commit SHA: abc123def456" in text
    assert "Environment: production" in text
    assert "Started at: 14.08.2026 08:00 UTC" in text
    assert "Uptime: 1h 2m" in text
    assert "BOT_TOKEN" not in text
    assert "DATABASE_URL" not in text


async def test_admin_errors_screen_contains_only_aggregates() -> None:
    callback = make_callback(111)

    await call_admin_callback(callback, AdminAction.ERRORS)

    text = callback.message.edit_text.await_args.args[0]
    assert "Ошибок за runtime: 3" in text
    assert "Подавлено уведомлений: 2" in text
    assert "Последняя ошибка: 14.08.2026 10:30 UTC" in text
    assert "Последний fingerprint: abc123" in text
    assert "Traceback" not in text


async def test_admin_close_deletes_panel_message() -> None:
    callback = make_callback(111)

    await call_admin_callback(callback, AdminAction.CLOSE)

    callback.answer.assert_awaited_once()
    callback.message.delete.assert_awaited_once()


async def test_admin_repository_returns_aggregate_stats() -> None:
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock(
        side_effect=[
            Mock(one=Mock(return_value=(100, 4, 20))),
            Mock(one=Mock(return_value=(10, 20, 30, 40, 2))),
            Mock(one=Mock(return_value=("16.4", "12 MB"))),
        ]
    )
    repository = AdminRepository(session)

    users = await repository.get_user_stats(datetime(2026, 8, 14, 12, 0, tzinfo=UTC))
    entities = await repository.get_entity_stats()
    database = await repository.get_database_info()

    assert users == AdminUserStats(100, 4, 20)
    assert entities == AdminEntityStats(10, 20, 30, 40, 2)
    assert database == AdminDatabaseInfo("16.4", "12 MB")
    assert session.execute.await_count == 3
