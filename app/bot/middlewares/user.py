from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.users import UserRepository
from app.services.users import TelegramUserData, UserService
from app.user_settings import NumberFormat
from app.utils.decimal import reset_number_format, set_number_format


class UserMiddleware(BaseMiddleware):
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        default_timezone: str,
    ) -> None:
        self._session_factory = session_factory
        self._default_timezone = default_timezone

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if not isinstance(telegram_user, TelegramUser):
            return await handler(event, data)

        async with self._session_factory() as session, session.begin():
            service = UserService(
                UserRepository(session),
                default_timezone=self._default_timezone,
            )
            sync_result = await service.sync_telegram_user(
                TelegramUserData(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name,
                    last_name=telegram_user.last_name,
                    language_code=telegram_user.language_code,
                )
            )
            data["current_user"] = sync_result.user
            data["is_new_user"] = sync_result.created
            data["db_session"] = session
            selected_format = NumberFormat(
                sync_result.user.number_format or NumberFormat.AUTOMATIC
            )
            token = set_number_format(selected_format)
            try:
                return await handler(event, data)
            finally:
                reset_number_format(token)
