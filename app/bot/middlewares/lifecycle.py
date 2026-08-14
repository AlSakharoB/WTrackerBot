import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.lifecycle import LifecycleManager

logger = logging.getLogger(__name__)


class LifecycleMiddleware(BaseMiddleware):
    def __init__(self, lifecycle: LifecycleManager) -> None:
        self._lifecycle = lifecycle

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self._lifecycle.begin_update():
            logger.info(
                "Telegram update ignored during shutdown",
                extra={"operation": "lifecycle.reject_update"},
            )
            return None
        try:
            return await handler(event, data)
        finally:
            self._lifecycle.finish_update()
