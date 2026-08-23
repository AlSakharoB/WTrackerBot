import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.states.dishes import DishSearchStates
from app.bot.states.ingredients import IngredientSearchStates
from app.bot.states.weights import WeightChartStates
from app.services.rate_limit import RateLimitScope, RateLimitService

logger = logging.getLogger(__name__)

RATE_LIMIT_TEXT = "Слишком много действий подряд. Попробуйте через несколько секунд."
SEARCH_STATES = {
    IngredientSearchStates.wait_query.state,
    DishSearchStates.wait_query.state,
}
WEIGHT_CHART_CALLBACK_PREFIXES = ("weight:chart", "weight_chart:", "wch:")
WEIGHT_CHART_STATES = {WeightChartStates.wait_date_to.state}
SHARE_CREATE_CALLBACKS = {"shsel:create", "shdsel:create"}
SHARE_CREATE_CALLBACK_PREFIXES = ("ingredient:share:", "dish:share:")
SHARE_IMPORT_ACTIONS = {
    "share_import",
    "share_keep",
    "share_copy",
    "share_batch",
    "share_dish",
    "share_dishes",
}
SHARE_ROTATE_ACTION = "share_rotate_manage"


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, service: RateLimitService) -> None:
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

        for scope in resolve_rate_limit_scopes(event, data):
            decision = self._service.check(user_id, scope)
            if not decision.allowed:
                await self._reject_update(
                    event,
                    user_id=user_id,
                    scope=scope,
                    retry_after_seconds=decision.retry_after_seconds,
                )
                return None
        return await handler(event, data)

    async def _reject_update(
        self,
        update: Update,
        *,
        user_id: int,
        scope: RateLimitScope,
        retry_after_seconds: float,
    ) -> None:
        send_notice = self._service.should_send_notice(user_id)
        if send_notice:
            logger.warning(
                "Rate limit triggered for scope=%s retry_after=%.1fs",
                scope.value,
                retry_after_seconds,
                extra={"operation": f"rate_limit.{scope.value}"},
            )

        callback = update.callback_query
        if callback is not None:
            await callback.answer(RATE_LIMIT_TEXT if send_notice else None)
        elif send_notice and update.message is not None:
            await update.message.answer(RATE_LIMIT_TEXT)


def resolve_rate_limit_scopes(
    update: Update,
    data: dict[str, Any],
) -> tuple[RateLimitScope, ...]:
    if update.message is not None:
        scopes = [RateLimitScope.MESSAGES]
        message_text = (
            update.message.text if isinstance(update.message.text, str) else ""
        )
        if _is_share_start(message_text):
            scopes.append(RateLimitScope.SHARE_OPEN)
        if data.get("raw_state") in SEARCH_STATES:
            scopes.append(RateLimitScope.SEARCH)
        if data.get("raw_state") in WEIGHT_CHART_STATES:
            scopes.append(RateLimitScope.WEIGHT_CHART)
        return tuple(scopes)

    callback = update.callback_query
    if callback is not None:
        scopes = [RateLimitScope.CALLBACKS]
        callback_data = callback.data or ""
        if callback_data.startswith(WEIGHT_CHART_CALLBACK_PREFIXES):
            scopes.append(RateLimitScope.WEIGHT_CHART)
        if callback_data in SHARE_CREATE_CALLBACKS or callback_data.startswith(
            SHARE_CREATE_CALLBACK_PREFIXES
        ):
            scopes.append(RateLimitScope.SHARE_CREATE)
        try:
            confirmation = ConfirmActionCallback.unpack(callback_data)
        except (TypeError, ValueError):
            confirmation = None
        if confirmation is not None:
            if confirmation.action in SHARE_IMPORT_ACTIONS:
                scopes.append(RateLimitScope.SHARE_IMPORT)
            elif confirmation.action == SHARE_ROTATE_ACTION:
                scopes.append(RateLimitScope.SHARE_ROTATE)
        return tuple(scopes)
    return ()


def _is_share_start(text: str) -> bool:
    fields = text.strip().split(maxsplit=1)
    return (
        len(fields) == 2
        and fields[0].split("@", maxsplit=1)[0] == "/start"
        and fields[1].startswith("sh_")
    )
