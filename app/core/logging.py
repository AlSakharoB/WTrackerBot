import logging
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import IO, Any
from urllib.parse import urlsplit

from app.config import Settings

LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | "
    "correlation_id=%(correlation_id)s | user_id=%(user_id)s | "
    "handler=%(handler)s | operation=%(operation)s | "
    "package_id=%(package_id)s | package_type=%(package_type)s | "
    "item_count=%(item_count)s | "
    "exception_type=%(exception_type)s | %(message)s"
)

_TELEGRAM_TOKEN_PATTERN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_DATABASE_URL_PATTERN = re.compile(
    r"(?P<scheme>postgres(?:ql)?(?:\+asyncpg)?://)[^@\s]+@",
    flags=re.IGNORECASE,
)
_SHARE_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])sh_[A-Za-z0-9_-]{32}(?![A-Za-z0-9_-])"
)


@dataclass(frozen=True, slots=True)
class LogContext:
    correlation_id: str | None = None
    user_id: int | None = None
    handler: str | None = None
    operation: str | None = None
    package_id: int | None = None
    package_type: str | None = None
    item_count: int | None = None


_log_context: ContextVar[LogContext | None] = ContextVar(
    "application_log_context",
    default=None,
)


@contextmanager
def logging_context(**values: Any) -> Iterator[None]:
    """Temporarily add safe request metadata to every log record."""
    current = _log_context.get() or LogContext()
    allowed_values = {
        key: value
        for key, value in values.items()
        if key in LogContext.__dataclass_fields__
    }
    token = _log_context.set(replace(current, **allowed_values))
    try:
        yield
    finally:
        _log_context.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _log_context.get() or LogContext()
        aiogram_update_id = _get_aiogram_update_id(record)
        values = {
            field: getattr(context, field) or "-"
            for field in LogContext.__dataclass_fields__
        }
        if aiogram_update_id is not None:
            values["correlation_id"] = f"tg-{aiogram_update_id}"
            values["handler"] = "aiogram.dispatcher.feed_update"
            values["operation"] = (
                "telegram.update.failed"
                if str(record.msg).startswith("Cause exception")
                else "telegram.update.completed"
            )
        for field in LogContext.__dataclass_fields__:
            if not hasattr(record, field):
                setattr(record, field, values[field])

        if not hasattr(record, "exception_type"):
            exception_type = "-"
            if record.exc_info and record.exc_info[0] is not None:
                exception_type = record.exc_info[0].__name__
            record.exception_type = exception_type
        return True


def _get_aiogram_update_id(record: logging.LogRecord) -> int | None:
    if record.name != "aiogram.event" or not isinstance(record.args, tuple):
        return None
    message_template = str(record.msg)
    if not message_template.startswith(("Update id=", "Cause exception")):
        return None
    if not record.args:
        return None
    update_id = record.args[0]
    return update_id if isinstance(update_id, int) else None


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str, *, secrets: tuple[str, ...]) -> None:
        super().__init__(fmt)
        self._secrets = tuple(
            secret for secret in sorted(set(secrets), key=len, reverse=True) if secret
        )

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        rendered = _TELEGRAM_TOKEN_PATTERN.sub("[REDACTED_BOT_TOKEN]", rendered)
        rendered = _DATABASE_URL_PATTERN.sub(
            r"\g<scheme>[REDACTED_CREDENTIALS]@",
            rendered,
        )
        rendered = _SHARE_TOKEN_PATTERN.sub("[REDACTED_SHARE_TOKEN]", rendered)
        for secret in self._secrets:
            rendered = rendered.replace(secret, "[REDACTED]")
        return rendered


def _known_secrets(settings: Settings) -> tuple[str, ...]:
    database_url = settings.database_url
    password = urlsplit(database_url).password
    return tuple(
        value
        for value in (
            settings.bot_token.get_secret_value(),
            database_url,
            password if password and len(password) >= 8 else None,
        )
        if value
    )


def setup_logging(settings: Settings, *, stream: IO[str] | None = None) -> None:
    """Configure one stdout logger for local and Docker execution."""
    handler = logging.StreamHandler(stream or sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(
        RedactingFormatter(LOG_FORMAT, secrets=_known_secrets(settings))
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.log_level)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
    logging.captureWarnings(True)


def flush_logging_handlers() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()
