import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

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
        return tuple(scopes)
    return ()
