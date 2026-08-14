import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.core.logging import logging_context

logger = logging.getLogger(__name__)


def _event_type(update: Update) -> str:
    try:
        return update.event_type
    except LookupError:
        return "unknown"


class CorrelationIdMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        correlation_id = f"tg-{event.update_id}"
        event_type = _event_type(event)
        telegram_user = data.get("event_from_user")
        user_id = getattr(telegram_user, "id", None)
        data["correlation_id"] = correlation_id

        with logging_context(
            correlation_id=correlation_id,
            user_id=user_id,
            handler="aiogram.dispatcher.feed_update",
            operation=f"telegram.{event_type}",
        ):
            started = perf_counter()
            try:
                result = await handler(event, data)
            except asyncio.CancelledError:
                logger.info(
                    "Telegram update cancelled during shutdown after %.1f ms",
                    (perf_counter() - started) * 1000,
                )
                raise
            except Exception as error:
                logger.warning(
                    "Telegram update failed after %.1f ms",
                    (perf_counter() - started) * 1000,
                    extra={"exception_type": type(error).__name__},
                )
                raise
            logger.info(
                "Telegram update handled in %.1f ms",
                (perf_counter() - started) * 1000,
            )
            return result
