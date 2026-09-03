from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.user import User
from app.repositories.users import UserRepository
from app.services.users import TelegramUserData, UserService
from app.web.auth import (
    TelegramInitDataError,
    TelegramInitDataValidator,
    ValidatedInitData,
)
from app.web.errors import AuthenticationError


def get_web_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.database_session_factory
    async with session_factory() as session, session.begin():
        yield session


def get_validated_init_data(
    request: Request,
    settings: Annotated[Settings, Depends(get_web_settings)],
) -> ValidatedInitData:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        raise AuthenticationError("Telegram authorization is required")
    if len(authorization.encode()) > settings.miniapp_max_auth_header_bytes:
        raise AuthenticationError("Telegram authorization header is too large")

    scheme, separator, raw_init_data = authorization.partition(" ")
    if not separator or scheme.lower() != "tma" or not raw_init_data:
        raise AuthenticationError("Telegram authorization scheme is invalid")

    validator: TelegramInitDataValidator = request.app.state.telegram_auth_validator
    try:
        return validator.validate(raw_init_data)
    except TelegramInitDataError as error:
        raise AuthenticationError() from error


async def get_current_user(
    request: Request,
    init_data: Annotated[ValidatedInitData, Depends(get_validated_init_data)],
    session: Annotated[AsyncSession, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_web_settings)],
) -> User:
    telegram_user = init_data.user
    result = await UserService(
        UserRepository(session),
        default_timezone=settings.default_timezone,
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
        )
    )
    request.state.user_id = result.user.id
    request.state.telegram_photo_url = telegram_user.photo_url
    return result.user


CurrentUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]
