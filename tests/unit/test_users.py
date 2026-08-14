from unittest.mock import AsyncMock, Mock

from app.db.models.user import User
from app.services.users import TelegramUserData, UserService


def make_telegram_data(**overrides: object) -> TelegramUserData:
    values = {
        "telegram_id": 123456789,
        "username": "nutrition_user",
        "first_name": "Иван",
        "last_name": "Иванов",
        "language_code": "ru",
    }
    values.update(overrides)
    return TelegramUserData(**values)  # type: ignore[arg-type]


async def test_sync_creates_unknown_user() -> None:
    user = User(id=1, telegram_id=123456789, timezone="Europe/Moscow")
    repository = Mock()
    repository.get_by_telegram_id = AsyncMock(return_value=None)
    repository.create_or_get = AsyncMock(return_value=(user, True))
    service = UserService(repository, default_timezone="Europe/Moscow")
    data = make_telegram_data()

    result = await service.sync_telegram_user(data)

    assert result.user is user
    assert result.created is True
    repository.create_or_get.assert_awaited_once_with(
        telegram_id=data.telegram_id,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        language_code=data.language_code,
        timezone="Europe/Moscow",
    )


async def test_sync_keeps_unchanged_existing_user() -> None:
    data = make_telegram_data()
    user = User(
        id=1,
        telegram_id=data.telegram_id,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        language_code=data.language_code,
        timezone="Europe/Moscow",
    )
    repository = Mock()
    repository.get_by_telegram_id = AsyncMock(return_value=user)
    service = UserService(repository, default_timezone="Europe/Moscow")

    result = await service.sync_telegram_user(data)

    assert result.user is user
    assert result.created is False
    repository.create_or_get.assert_not_called()
    repository.update_telegram_data.assert_not_called()


async def test_sync_updates_changed_telegram_data() -> None:
    user = User(
        id=1,
        telegram_id=123456789,
        username="old_name",
        first_name="Old",
        last_name=None,
        language_code="en",
        timezone="Europe/Moscow",
    )
    repository = Mock()
    repository.get_by_telegram_id = AsyncMock(return_value=user)
    service = UserService(repository, default_timezone="Europe/Moscow")
    data = make_telegram_data()

    result = await service.sync_telegram_user(data)

    assert result.created is False
    repository.update_telegram_data.assert_called_once_with(
        user,
        username=data.username,
        first_name=data.first_name,
        last_name=data.last_name,
        language_code=data.language_code,
    )
