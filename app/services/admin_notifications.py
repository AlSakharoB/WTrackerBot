import asyncio
import hashlib
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from time import monotonic

from aiogram.enums import ParseMode

from app.exceptions import AppError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErrorRuntimeStats:
    total_errors: int
    last_error_at: datetime | None
    last_fingerprint: str | None
    suppressed_notifications: int


@dataclass(slots=True)
class _FingerprintState:
    last_sent_at: float | None = None
    suppressed_count: int = 0


class AdminNotificationService:
    def __init__(
        self,
        bot: object,
        admin_telegram_ids: set[int],
        *,
        cooldown_seconds: int,
        max_per_minute: int,
        monotonic_clock: Callable[[], float] = monotonic,
        utcnow: Callable[[], datetime] | None = None,
    ) -> None:
        self._bot = bot
        self._admin_telegram_ids = frozenset(admin_telegram_ids)
        self._cooldown_seconds = cooldown_seconds
        self._max_per_minute = max_per_minute
        self._monotonic_clock = monotonic_clock
        self._utcnow = utcnow or (lambda: datetime.now(UTC))
        self._fingerprints: dict[str, _FingerprintState] = {}
        self._sent_timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._total_errors = 0
        self._last_error_at: datetime | None = None
        self._last_fingerprint: str | None = None
        self._suppressed_notifications = 0

    @property
    def stats(self) -> ErrorRuntimeStats:
        return ErrorRuntimeStats(
            total_errors=self._total_errors,
            last_error_at=self._last_error_at,
            last_fingerprint=self._last_fingerprint,
            suppressed_notifications=self._suppressed_notifications,
        )

    async def notify_error(
        self,
        error: Exception,
        correlation_id: str | None,
        operation: str | None,
        user_id: int | None,
    ) -> None:
        if isinstance(error, AppError):
            return

        fingerprint = build_error_fingerprint(error, operation)
        occurred_at = self._utcnow()
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=UTC)
        else:
            occurred_at = occurred_at.astimezone(UTC)

        async with self._lock:
            self._total_errors += 1
            self._last_error_at = occurred_at
            self._last_fingerprint = fingerprint

            if not self._admin_telegram_ids:
                return

            now = self._monotonic_clock()
            state = self._fingerprints.setdefault(
                fingerprint,
                _FingerprintState(),
            )
            if (
                state.last_sent_at is not None
                and now - state.last_sent_at < self._cooldown_seconds
            ):
                state.suppressed_count += 1
                self._suppressed_notifications += 1
                return

            self._discard_old_alert_timestamps(now)
            if len(self._sent_timestamps) >= self._max_per_minute:
                state.suppressed_count += 1
                self._suppressed_notifications += 1
                logger.warning(
                    "Admin notification rate limit triggered",
                    extra={"operation": "admin_notifications.rate_limit"},
                )
                return

            suppressed_count = state.suppressed_count
            state.suppressed_count = 0
            state.last_sent_at = now
            self._sent_timestamps.append(now)

        text = _build_notification_text(
            error=error,
            correlation_id=correlation_id,
            operation=operation,
            user_id=user_id,
            occurred_at=occurred_at,
            fingerprint=fingerprint,
            suppressed_count=suppressed_count,
        )
        for admin_id in sorted(self._admin_telegram_ids):
            try:
                await self._bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as send_error:
                logger.error(
                    "Failed to send admin error notification",
                    extra={
                        "operation": "admin_notifications.send",
                        "user_id": admin_id,
                        "exception_type": type(send_error).__name__,
                    },
                )

    def _discard_old_alert_timestamps(self, now: float) -> None:
        while self._sent_timestamps and now - self._sent_timestamps[0] >= 60:
            self._sent_timestamps.popleft()


def build_error_fingerprint(error: Exception, operation: str | None) -> str:
    traceback = error.__traceback__
    frame = "no_traceback"
    while traceback is not None:
        code = traceback.tb_frame.f_code
        frame = f"{code.co_filename}:{code.co_name}:{traceback.tb_lineno}"
        traceback = traceback.tb_next
    source = f"{type(error).__name__}|{operation or 'unknown'}|{frame}"
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def _build_notification_text(
    *,
    error: Exception,
    correlation_id: str | None,
    operation: str | None,
    user_id: int | None,
    occurred_at: datetime,
    fingerprint: str,
    suppressed_count: int,
) -> str:
    lines = [
        "🚨 <b>Ошибка бота</b>",
        "",
        f"Тип: {escape(type(error).__name__)}",
        f"Операция: {escape(operation or 'не указана')}",
        f"Correlation ID: {escape(correlation_id or 'нет')}",
        f"User ID: {user_id if user_id is not None else 'нет'}",
        f"Время: {occurred_at:%d.%m.%Y %H:%M} UTC",
        f"Fingerprint: <code>{fingerprint}</code>",
    ]
    if suppressed_count:
        lines.append(f"Подавлено повторов: {suppressed_count}")
    lines.extend(("", "Смотрите server logs для traceback."))
    return "\n".join(lines)
