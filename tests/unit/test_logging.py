import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from aiogram.types import Chat, Message, Update, User

from app.bot.handlers.common import global_error_handler
from app.bot.middlewares.correlation import CorrelationIdMiddleware
from app.config import Settings
from app.core.logging import flush_logging_handlers, logging_context, setup_logging
from app.services.admin_notifications import AdminNotificationService

VALID_SETTINGS = {
    "bot_token": "123456789:abcdefghijklmnopqrstuvwxyzABCDE1234567890",
    "database_url": (
        "postgresql+asyncpg://nutrition:very-secret-password@db/nutrition_bot"
    ),
}


@contextmanager
def configured_logging(*, level: str = "INFO") -> Iterator[io.StringIO]:
    root_logger = logging.getLogger()
    aiogram_event_logger = logging.getLogger("aiogram.event")
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level
    previous_aiogram_event_level = aiogram_event_logger.level
    output = io.StringIO()
    settings = Settings(
        **VALID_SETTINGS,
        log_level=level,
        _env_file=None,
    )
    setup_logging(settings, stream=output)
    try:
        yield output
    finally:
        root_logger.handlers[:] = previous_handlers
        root_logger.setLevel(previous_level)
        aiogram_event_logger.setLevel(previous_aiogram_event_level)


def test_setup_logging_respects_log_level_and_adds_context() -> None:
    logger = logging.getLogger("tests.logging")

    with configured_logging(level="DEBUG") as output:
        with logging_context(
            correlation_id="tg-42",
            user_id=7,
            handler="tests.handler",
            operation="diary.add_food",
        ):
            logger.debug("Operation accepted")

    rendered = output.getvalue()
    assert "DEBUG | tests.logging" in rendered
    assert "correlation_id=tg-42" in rendered
    assert "user_id=7" in rendered
    assert "handler=tests.handler" in rendered
    assert "operation=diary.add_food" in rendered


def test_setup_logging_redacts_known_and_pattern_secrets() -> None:
    logger = logging.getLogger("tests.logging")
    token = VALID_SETTINGS["bot_token"]
    database_url = VALID_SETTINGS["database_url"]

    with configured_logging() as output:
        logger.error("token=%s database=%s", token, database_url)

    rendered = output.getvalue()
    assert token not in rendered
    assert database_url not in rendered
    assert "very-secret-password" not in rendered
    assert "[REDACTED" in rendered


def test_aiogram_completion_info_is_suppressed_to_avoid_duplicate_logs() -> None:
    logger = logging.getLogger("aiogram.event")

    with configured_logging() as output:
        logger.info(
            "Update id=%s is %s. Duration %d ms by bot id=%d",
            150703164,
            "handled",
            227,
            8652255702,
        )

    assert output.getvalue() == ""


def test_aiogram_failure_log_recovers_update_correlation_id() -> None:
    logger = logging.getLogger("aiogram.event")

    with configured_logging() as output:
        try:
            raise RuntimeError("controlled failure")
        except RuntimeError:
            logger.exception(
                "Cause exception while process update id=%d by bot id=%d",
                150703165,
                8652255702,
            )

    rendered = output.getvalue()
    assert "correlation_id=tg-150703165" in rendered
    assert "operation=telegram.update.failed" in rendered
    assert "exception_type=RuntimeError" in rendered


async def test_correlation_middleware_sets_and_resets_update_context() -> None:
    middleware = CorrelationIdMiddleware()
    update = Update(
        update_id=1234,
        message=Message(
            message_id=10,
            date=datetime.now(UTC),
            chat=Chat(id=55, type="private"),
            from_user=User(id=55, is_bot=False, first_name="Test"),
        ),
    )
    logger = logging.getLogger("tests.middleware")

    async def handler(_event: object, data: dict[str, object]) -> None:
        assert data["correlation_id"] == "tg-1234"
        logger.info("Inside update")

    with configured_logging() as output:
        await middleware(handler, update, {"event_from_user": update.message.from_user})
        logger.info("Outside update")

    lines = output.getvalue().splitlines()
    assert "correlation_id=tg-1234" in lines[0]
    assert "user_id=55" in lines[0]
    assert "operation=telegram.message" in lines[0]
    assert "Telegram update handled" in lines[1]
    assert "correlation_id=tg-1234" in lines[1]
    assert "user_id=55" in lines[1]
    assert "handler=aiogram.dispatcher.feed_update" in lines[1]
    assert "correlation_id=-" in lines[2]


async def test_unhandled_exception_logs_traceback_but_sends_safe_message() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.from_user = User(id=77, is_bot=False, first_name="Test")
    try:
        raise RuntimeError("controlled failure")
    except RuntimeError as exception:
        event = SimpleNamespace(
            exception=exception,
            update=SimpleNamespace(
                update_id=987,
                message=message,
                callback_query=None,
            ),
        )

        with configured_logging() as output:
            handled = await global_error_handler(event)  # type: ignore[arg-type]

    rendered = output.getvalue()
    assert handled is True
    assert "Unhandled handler exception" in rendered
    assert "correlation_id=tg-987" in rendered
    assert "user_id=77" in rendered
    assert "exception_type=RuntimeError" in rendered
    assert "Traceback (most recent call last)" in rendered
    user_text = message.answer.await_args.args[0]
    assert user_text == "Произошла внутренняя ошибка. Повторите действие позже."
    assert "Traceback" not in user_text
    assert "controlled failure" not in user_text


async def test_controlled_exception_is_logged_and_alerted_with_correlation_id() -> None:
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    message.from_user = User(id=77, is_bot=False, first_name="Test")
    bot = Mock(send_message=AsyncMock())
    notifications = AdminNotificationService(
        bot,
        {111},
        cooldown_seconds=300,
        max_per_minute=10,
    )
    try:
        raise RuntimeError(
            f"controlled {VALID_SETTINGS['bot_token']} {VALID_SETTINGS['database_url']}"
        )
    except RuntimeError as exception:
        event = SimpleNamespace(
            exception=exception,
            update=SimpleNamespace(
                update_id=19001,
                message=message,
                callback_query=None,
            ),
        )

        with configured_logging() as output:
            await global_error_handler(  # type: ignore[arg-type]
                event,
                admin_notification_service=notifications,
            )

    server_log = output.getvalue()
    alert = bot.send_message.await_args.kwargs["text"]
    assert "correlation_id=tg-19001" in server_log
    assert "exception_type=RuntimeError" in server_log
    assert "Correlation ID: tg-19001" in alert
    assert "User ID: 77" in alert
    for secret in VALID_SETTINGS.values():
        assert secret not in server_log
        assert secret not in alert


def test_docker_compose_configures_json_file_rotation() -> None:
    compose = Path(__file__).parents[2].joinpath("docker-compose.yml").read_text()

    assert "driver: json-file" in compose
    assert "max-size: 10m" in compose
    assert 'max-file: "5"' in compose


def test_flush_logging_handlers_flushes_root_handlers() -> None:
    root_logger = logging.getLogger()
    handlers = root_logger.handlers[:]
    handler = Mock()
    root_logger.handlers[:] = [handler]
    try:
        flush_logging_handlers()
    finally:
        root_logger.handlers[:] = handlers

    handler.flush.assert_called_once()
