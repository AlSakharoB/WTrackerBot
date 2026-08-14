import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.bot.keyboards.actions import ConfirmActionCallback
from app.services.action_lock import ActionLockService

logger = logging.getLogger(__name__)

ACTION_IN_PROGRESS_TEXT = "Действие уже обрабатывается или выполнено."


def resolve_action_lock_key(update: Update, user_id: int) -> str | None:
    callback = update.callback_query
    if callback is None or not callback.data:
        return None

    try:
        action = ConfirmActionCallback.unpack(callback.data)
    except (TypeError, ValueError):
        action = None
    if action is not None:
        return f"{user_id}:{action.action}:{action.token}"

    fields = callback.data.split(":")
    if any(field.endswith("_confirm") for field in fields):
        return f"{user_id}:{callback.data}"
    return None


class ActionLockMiddleware(BaseMiddleware):
    def __init__(self, service: ActionLockService) -> None:
        self._service = service

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        telegram_user = data.get("event_from_user")
        user_id = getattr(telegram_user, "id", None)
        if not isinstance(user_id, int):
            return await handler(event, data)

        key = resolve_action_lock_key(event, user_id)
        if key is None:
            return await handler(event, data)
        lease = self._service.acquire(key)
        if lease is None:
            logger.warning(
                "Duplicate callback action ignored",
                extra={"operation": "action_lock.duplicate"},
            )
            callback = event.callback_query
            if callback is not None:
                await callback.answer(ACTION_IN_PROGRESS_TEXT)
            return None

        try:
            return await handler(event, data)
        except BaseException:
            self._service.release(lease)
            raise
