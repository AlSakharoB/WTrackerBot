import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Protocol

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

HEARTBEAT_FILE = Path("/tmp/nutrition-bot-heartbeat")


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class DatabaseRevisionStatus(StrEnum):
    UP_TO_DATE = "up_to_date"
    BEHIND = "behind"
    AHEAD_UNKNOWN = "ahead_unknown"


@dataclass(frozen=True, slots=True)
class DatabaseRevisionState:
    current: tuple[str, ...]
    expected: tuple[str, ...]
    status: DatabaseRevisionStatus


class DatabaseRevisionMismatchError(RuntimeError):
    def __init__(self, state: DatabaseRevisionState) -> None:
        self.state = state
        current = ",".join(state.current) or "none"
        expected = ",".join(state.expected) or "none"
        super().__init__(
            f"Database revision is {state.status.value}: "
            f"current={current}, expected={expected}"
        )


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    component: str
    status: HealthStatus
    message: str
    latency_ms: float | None = None
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealthReport:
    status: HealthStatus
    checks: tuple[HealthCheckResult, ...]
    started_at: datetime
    generated_at: datetime

    @property
    def uptime_seconds(self) -> int:
        return max(0, int((self.generated_at - self.started_at).total_seconds()))


@dataclass(slots=True)
class HealthState:
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_app_heartbeat: datetime | None = None

    def touch(self, now: datetime | None = None) -> None:
        self.last_app_heartbeat = now or datetime.now(UTC)


class TelegramHealthClient(Protocol):
    async def get_me(self) -> object: ...


class SchedulerHealthClient(Protocol):
    @property
    def running(self) -> bool: ...

    @property
    def job_count(self) -> int: ...

    @property
    def last_heartbeat(self) -> datetime | None: ...

    @property
    def next_job_time(self) -> datetime | None: ...


def get_expected_database_heads() -> tuple[str, ...]:
    project_root = Path.cwd()
    if not project_root.joinpath("alembic.ini").is_file():
        project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def get_database_revision_status(
    current_heads: tuple[str, ...],
    expected_heads: tuple[str, ...],
) -> DatabaseRevisionStatus:
    if current_heads == expected_heads:
        return DatabaseRevisionStatus.UP_TO_DATE
    if not current_heads:
        return DatabaseRevisionStatus.BEHIND

    project_root = Path.cwd()
    if not project_root.joinpath("alembic.ini").is_file():
        project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    revisions = ScriptDirectory.from_config(config)
    try:
        for revision in current_heads:
            revisions.get_revision(revision)
        ancestors = {
            revision.revision
            for expected in expected_heads
            for revision in revisions.walk_revisions(base="base", head=expected)
        }
    except CommandError:
        return DatabaseRevisionStatus.AHEAD_UNKNOWN
    if all(current in ancestors for current in current_heads):
        return DatabaseRevisionStatus.BEHIND
    return DatabaseRevisionStatus.AHEAD_UNKNOWN


async def get_current_database_heads(engine: AsyncEngine) -> tuple[str, ...]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT version_num FROM alembic_version")
        )
        return tuple(sorted(result.scalars().all()))


async def get_database_revision_state(
    engine: AsyncEngine,
) -> DatabaseRevisionState:
    current = await get_current_database_heads(engine)
    expected = get_expected_database_heads()
    return DatabaseRevisionState(
        current=current,
        expected=expected,
        status=get_database_revision_status(current, expected),
    )


async def ensure_database_revision_current(
    engine: AsyncEngine,
) -> DatabaseRevisionState:
    state = await get_database_revision_state(engine)
    if state.status is not DatabaseRevisionStatus.UP_TO_DATE:
        raise DatabaseRevisionMismatchError(state)
    return state


class HealthService:
    def __init__(
        self,
        engine: AsyncEngine,
        bot: TelegramHealthClient,
        state: HealthState,
        *,
        heartbeat_stale_after_seconds: int,
        scheduler: SchedulerHealthClient | None = None,
    ) -> None:
        self._engine = engine
        self._bot = bot
        self._state = state
        self._heartbeat_stale_after_seconds = heartbeat_stale_after_seconds
        self._scheduler = scheduler

    @property
    def started_at(self) -> datetime:
        return self._state.started_at

    @property
    def uptime_seconds(self) -> int:
        return max(0, int((datetime.now(UTC) - self._state.started_at).total_seconds()))

    async def check_database(self) -> HealthCheckResult:
        started = perf_counter()
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception as error:
            logger.warning(
                "Database health check failed",
                exc_info=True,
                extra={"operation": "health.database"},
            )
            return HealthCheckResult(
                component="database",
                status=HealthStatus.ERROR,
                message=type(error).__name__,
                latency_ms=_elapsed_ms(started),
            )
        return HealthCheckResult(
            component="database",
            status=HealthStatus.OK,
            message="available",
            latency_ms=_elapsed_ms(started),
        )

    async def check_telegram(self) -> HealthCheckResult:
        started = perf_counter()
        try:
            await self._bot.get_me()
        except Exception as error:
            logger.warning(
                "Telegram health check failed",
                exc_info=True,
                extra={"operation": "health.telegram"},
            )
            return HealthCheckResult(
                component="telegram",
                status=HealthStatus.ERROR,
                message=type(error).__name__,
                latency_ms=_elapsed_ms(started),
            )
        return HealthCheckResult(
            component="telegram",
            status=HealthStatus.OK,
            message="available",
            latency_ms=_elapsed_ms(started),
        )

    async def check_scheduler(self) -> HealthCheckResult:
        if self._scheduler is None:
            return HealthCheckResult(
                component="scheduler",
                status=HealthStatus.OK,
                message="not_configured",
            )
        running = self._scheduler.running
        heartbeat = self._scheduler.last_heartbeat
        heartbeat_age = (
            None
            if heartbeat is None
            else max(0, (datetime.now(UTC) - heartbeat).total_seconds())
        )
        heartbeat_fresh = (
            heartbeat_age is not None
            and heartbeat_age <= self._heartbeat_stale_after_seconds
        )
        next_job_time = self._scheduler.next_job_time
        if not running:
            message = "stopped"
        elif not heartbeat_fresh:
            message = "heartbeat_stale"
        else:
            message = "running"
        return HealthCheckResult(
            component="scheduler",
            status=(
                HealthStatus.OK if running and heartbeat_fresh else HealthStatus.ERROR
            ),
            message=message,
            details={
                "scheduler_running": str(running).lower(),
                "last_scheduler_heartbeat": (
                    heartbeat.isoformat() if heartbeat is not None else "none"
                ),
                "next_job_time": (
                    next_job_time.isoformat() if next_job_time is not None else "none"
                ),
                "jobs": str(self._scheduler.job_count),
            },
        )

    async def check_database_revision(self) -> HealthCheckResult:
        started = perf_counter()
        try:
            revision = await get_database_revision_state(self._engine)
        except Exception as error:
            logger.warning(
                "Database revision health check failed",
                exc_info=True,
                extra={"operation": "health.database_revision"},
            )
            return HealthCheckResult(
                component="database_revision",
                status=HealthStatus.ERROR,
                message=type(error).__name__,
                latency_ms=_elapsed_ms(started),
            )

        details = {
            "current": ",".join(revision.current) or "none",
            "expected": ",".join(revision.expected) or "none",
        }
        status = {
            DatabaseRevisionStatus.UP_TO_DATE: HealthStatus.OK,
            DatabaseRevisionStatus.BEHIND: HealthStatus.DEGRADED,
            DatabaseRevisionStatus.AHEAD_UNKNOWN: HealthStatus.ERROR,
        }[revision.status]
        return HealthCheckResult(
            component="database_revision",
            status=status,
            message=revision.status.value,
            latency_ms=_elapsed_ms(started),
            details=details,
        )

    async def check_heartbeat(self) -> HealthCheckResult:
        heartbeat = self._state.last_app_heartbeat
        if heartbeat is None:
            return HealthCheckResult(
                component="bot",
                status=HealthStatus.ERROR,
                message="missing",
            )
        age_seconds = max(0, (datetime.now(UTC) - heartbeat).total_seconds())
        status = (
            HealthStatus.ERROR
            if age_seconds > self._heartbeat_stale_after_seconds
            else HealthStatus.OK
        )
        return HealthCheckResult(
            component="bot",
            status=status,
            message="stale" if status is HealthStatus.ERROR else "fresh",
            details={"age_seconds": str(round(age_seconds, 1))},
        )

    async def get_full_health(self) -> HealthReport:
        checks = (
            await self.check_heartbeat(),
            await self.check_database(),
            await self.check_telegram(),
            await self.check_scheduler(),
            await self.check_database_revision(),
        )
        return HealthReport(
            status=_aggregate_status(checks),
            checks=checks,
            started_at=self._state.started_at,
            generated_at=datetime.now(UTC),
        )


def _aggregate_status(checks: tuple[HealthCheckResult, ...]) -> HealthStatus:
    if any(check.status is HealthStatus.ERROR for check in checks):
        return HealthStatus.ERROR
    if any(check.status is HealthStatus.DEGRADED for check in checks):
        return HealthStatus.DEGRADED
    return HealthStatus.OK


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 1)


def format_health_report(report: HealthReport) -> str:
    headings = {
        HealthStatus.OK: "🟢 HEALTHY",
        HealthStatus.DEGRADED: "🟡 DEGRADED",
        HealthStatus.ERROR: "🔴 UNHEALTHY",
    }
    component_labels = {
        "bot": "Bot",
        "database": "Database",
        "telegram": "Telegram",
        "scheduler": "Scheduler",
        "database_revision": "DB revision",
    }
    lines = [headings[report.status], ""]
    for check in report.checks:
        latency = (
            f" · {check.latency_ms:.1f} ms" if check.latency_ms is not None else ""
        )
        label = component_labels.get(check.component, check.component)
        lines.append(
            f"{label}: {check.status.value.upper()} ({check.message}){latency}"
        )
    lines.append(f"Uptime: {_format_uptime(report.uptime_seconds)}")
    return "\n".join(lines)


def _format_uptime(seconds: int) -> str:
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"


def _touch_heartbeat_file(path: Path) -> None:
    path.touch(exist_ok=True)


def _remove_heartbeat_file(path: Path) -> None:
    path.unlink(missing_ok=True)


async def run_app_heartbeat(
    state: HealthState,
    interval_seconds: int,
    *,
    heartbeat_file: Path = HEARTBEAT_FILE,
) -> None:
    try:
        while True:
            state.touch()
            try:
                _touch_heartbeat_file(heartbeat_file)
            except OSError:
                logger.exception(
                    "Failed to update app heartbeat file",
                    extra={"operation": "health.heartbeat"},
                )
            await asyncio.sleep(interval_seconds)
    finally:
        try:
            _remove_heartbeat_file(heartbeat_file)
        except OSError:
            logger.exception(
                "Failed to remove app heartbeat file",
                extra={"operation": "health.heartbeat"},
            )
