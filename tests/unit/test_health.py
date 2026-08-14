import asyncio
import os
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.core.health import (
    DatabaseRevisionStatus,
    HealthCheckResult,
    HealthReport,
    HealthService,
    HealthState,
    HealthStatus,
    format_health_report,
    get_database_revision_status,
    get_expected_database_heads,
    run_app_heartbeat,
)
from scripts import healthcheck


def make_engine(*, execute_result: object | None = None) -> tuple[Mock, AsyncMock]:
    connection = AsyncMock()
    connection.execute = AsyncMock(return_value=execute_result)
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = connection
    engine = Mock()
    engine.connect.return_value = context_manager
    engine.dispose = AsyncMock()
    return engine, connection


def make_service(
    *,
    engine: Mock | None = None,
    bot: Mock | None = None,
    state: HealthState | None = None,
    stale_after: int = 90,
) -> HealthService:
    if engine is None:
        engine, _ = make_engine()
    if bot is None:
        bot = Mock(get_me=AsyncMock())
    return HealthService(
        engine,
        bot,
        state or HealthState(last_app_heartbeat=datetime.now(UTC)),
        heartbeat_stale_after_seconds=stale_after,
    )


async def test_database_health_ok() -> None:
    engine, connection = make_engine()
    service = make_service(engine=engine)

    result = await service.check_database()

    assert result.status is HealthStatus.OK
    assert result.message == "available"
    assert result.latency_ms is not None
    connection.execute.assert_awaited_once()


async def test_database_health_reports_unavailable() -> None:
    engine, _ = make_engine()
    engine.connect.return_value.__aenter__.side_effect = OSError("db unavailable")
    service = make_service(engine=engine)

    result = await service.check_database()

    assert result.status is HealthStatus.ERROR
    assert result.message == "OSError"


async def test_telegram_health_ok_and_failure() -> None:
    bot = Mock(get_me=AsyncMock())
    service = make_service(bot=bot)

    successful = await service.check_telegram()
    bot.get_me.side_effect = RuntimeError("telegram unavailable")
    failed = await service.check_telegram()

    assert successful.status is HealthStatus.OK
    assert failed.status is HealthStatus.ERROR
    assert failed.message == "RuntimeError"


async def test_scheduler_is_not_configured_without_degrading_health() -> None:
    result = await make_service().check_scheduler()

    assert result.status is HealthStatus.OK
    assert result.message == "not_configured"


async def test_scheduler_health_reports_runtime_state() -> None:
    now = datetime.now(UTC)
    next_job = now + timedelta(hours=1)
    scheduler = SimpleNamespace(
        running=True,
        job_count=3,
        last_heartbeat=now,
        next_job_time=next_job,
    )
    engine, _ = make_engine()
    service = HealthService(
        engine,
        Mock(get_me=AsyncMock()),
        HealthState(last_app_heartbeat=datetime.now(UTC)),
        heartbeat_stale_after_seconds=90,
        scheduler=scheduler,
    )

    running = await service.check_scheduler()
    scheduler.running = False
    stopped = await service.check_scheduler()

    assert running.status is HealthStatus.OK
    assert running.message == "running"
    assert running.details == {
        "scheduler_running": "true",
        "last_scheduler_heartbeat": now.isoformat(),
        "next_job_time": next_job.isoformat(),
        "jobs": "3",
    }
    assert stopped.status is HealthStatus.ERROR
    assert stopped.message == "stopped"


async def test_scheduler_health_reports_stale_heartbeat() -> None:
    scheduler = SimpleNamespace(
        running=True,
        job_count=0,
        last_heartbeat=datetime.now(UTC) - timedelta(seconds=91),
        next_job_time=None,
    )
    engine, _ = make_engine()
    service = HealthService(
        engine,
        Mock(get_me=AsyncMock()),
        HealthState(last_app_heartbeat=datetime.now(UTC)),
        heartbeat_stale_after_seconds=90,
        scheduler=scheduler,
    )

    result = await service.check_scheduler()

    assert result.status is HealthStatus.ERROR
    assert result.message == "heartbeat_stale"
    assert result.details["next_job_time"] == "none"


async def test_database_revision_matches_code_head(monkeypatch) -> None:
    expected_head = get_expected_database_heads()[0]
    scalar_result = Mock()
    scalar_result.scalars.return_value.all.return_value = [expected_head]
    engine, _ = make_engine(execute_result=scalar_result)
    service = make_service(engine=engine)
    monkeypatch.setattr(
        "app.core.health.get_expected_database_heads",
        lambda: (expected_head,),
    )

    result = await service.check_database_revision()

    assert result.status is HealthStatus.OK
    assert result.message == "up_to_date"
    assert result.details == {"current": expected_head, "expected": expected_head}


async def test_database_revision_reports_mismatch(monkeypatch) -> None:
    scalar_result = Mock()
    scalar_result.scalars.return_value.all.return_value = ["unexpected"]
    engine, _ = make_engine(execute_result=scalar_result)
    service = make_service(engine=engine)
    monkeypatch.setattr(
        "app.core.health.get_expected_database_heads",
        lambda: ("expected",),
    )

    result = await service.check_database_revision()

    assert result.status is HealthStatus.ERROR
    assert result.message == "ahead_unknown"


def test_database_revision_status_distinguishes_behind_and_unknown() -> None:
    expected = get_expected_database_heads()

    assert (
        get_database_revision_status(("20260814_0009",), expected)
        is DatabaseRevisionStatus.BEHIND
    )
    assert (
        get_database_revision_status(("future_revision",), expected)
        is DatabaseRevisionStatus.AHEAD_UNKNOWN
    )


async def test_stale_heartbeat_is_unhealthy() -> None:
    state = HealthState(last_app_heartbeat=datetime.now(UTC) - timedelta(seconds=91))
    service = make_service(state=state, stale_after=90)

    result = await service.check_heartbeat()

    assert result.status is HealthStatus.ERROR
    assert result.message == "stale"


async def test_full_health_aggregates_status_and_formats_report(monkeypatch) -> None:
    service = make_service()
    ok = HealthCheckResult("database", HealthStatus.OK, "available", 8.0)
    degraded = HealthCheckResult(
        "database_revision",
        HealthStatus.DEGRADED,
        "behind",
    )
    monkeypatch.setattr(service, "check_heartbeat", AsyncMock(return_value=ok))
    monkeypatch.setattr(service, "check_database", AsyncMock(return_value=ok))
    monkeypatch.setattr(service, "check_telegram", AsyncMock(return_value=ok))
    monkeypatch.setattr(service, "check_scheduler", AsyncMock(return_value=ok))
    monkeypatch.setattr(
        service,
        "check_database_revision",
        AsyncMock(return_value=degraded),
    )

    report = await service.get_full_health()
    rendered = format_health_report(report)

    assert report.status is HealthStatus.DEGRADED
    assert "🟡 DEGRADED" in rendered
    assert "Database: OK (available) · 8.0 ms" in rendered
    assert "Uptime:" in rendered


async def test_heartbeat_loop_updates_state_and_cleans_file(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    state = HealthState()
    task = asyncio.create_task(
        run_app_heartbeat(state, 3600, heartbeat_file=heartbeat_file)
    )
    await asyncio.sleep(0)

    assert state.last_app_heartbeat is not None
    assert heartbeat_file.exists()

    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
    assert not heartbeat_file.exists()


def test_healthcheck_recognizes_fresh_and_stale_file(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    heartbeat_file.touch()

    assert healthcheck.heartbeat_file_is_fresh(
        heartbeat_file,
        stale_after_seconds=90,
    )

    old_timestamp = datetime.now(UTC).timestamp() - 91
    os.utime(heartbeat_file, (old_timestamp, old_timestamp))
    assert not healthcheck.heartbeat_file_is_fresh(
        heartbeat_file,
        stale_after_seconds=90,
    )


async def test_healthcheck_exit_codes(monkeypatch, tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    heartbeat_file.touch()
    engine = Mock(dispose=AsyncMock())
    database_check = AsyncMock()
    monkeypatch.setattr(healthcheck, "HEARTBEAT_FILE", heartbeat_file)
    monkeypatch.setattr(
        healthcheck,
        "get_settings",
        lambda: SimpleNamespace(
            health_heartbeat_interval_seconds=30,
            database_url="postgresql+asyncpg://user:pass@db/database",
        ),
    )
    monkeypatch.setattr(healthcheck, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(healthcheck, "check_database_connection", database_check)
    monkeypatch.setattr(
        healthcheck,
        "get_database_revision_state",
        AsyncMock(
            return_value=SimpleNamespace(status=DatabaseRevisionStatus.UP_TO_DATE)
        ),
    )

    assert await healthcheck.run_healthcheck() == 0

    database_check.side_effect = OSError("database unavailable")
    assert await healthcheck.run_healthcheck() == 1
    assert engine.dispose.await_count == 2


async def test_healthcheck_rejects_database_revision_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    heartbeat_file = tmp_path / "heartbeat"
    heartbeat_file.touch()
    engine = Mock(dispose=AsyncMock())
    monkeypatch.setattr(healthcheck, "HEARTBEAT_FILE", heartbeat_file)
    monkeypatch.setattr(
        healthcheck,
        "get_settings",
        lambda: SimpleNamespace(
            health_heartbeat_interval_seconds=30,
            database_url="postgresql+asyncpg://user:pass@db/database",
        ),
    )
    monkeypatch.setattr(healthcheck, "create_database_engine", lambda _: engine)
    monkeypatch.setattr(healthcheck, "check_database_connection", AsyncMock())
    monkeypatch.setattr(
        healthcheck,
        "get_database_revision_state",
        AsyncMock(return_value=SimpleNamespace(status=DatabaseRevisionStatus.BEHIND)),
    )

    assert await healthcheck.run_healthcheck() == 1
    engine.dispose.assert_awaited_once()


def test_health_report_uptime_never_negative() -> None:
    now = datetime.now(UTC)
    report = HealthReport(
        status=HealthStatus.OK,
        checks=(),
        started_at=now + timedelta(seconds=10),
        generated_at=now,
    )

    assert report.uptime_seconds == 0


def test_docker_image_and_compose_include_healthcheck() -> None:
    project_root = Path(__file__).parents[2]
    compose = project_root.joinpath("docker-compose.yml").read_text()
    dockerfile = project_root.joinpath("Dockerfile").read_text()

    assert 'test: ["CMD", "python", "scripts/healthcheck.py"]' in compose
    assert "interval: 30s" in compose
    assert "timeout: 10s" in compose
    assert "retries: 3" in compose
    assert "start_period: 20s" in compose
    assert "COPY scripts ./scripts" in dockerfile
