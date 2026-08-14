from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.repositories.users import UserRepository
from app.services.users import TelegramUserData, UserService


async def test_first_sync_creates_user_and_second_sync_reuses_it(
    session: AsyncSession,
) -> None:
    service = UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    )
    data = TelegramUserData(
        telegram_id=9123456789,
        username="integration_user",
        first_name="Integration",
        last_name="Test",
        language_code="ru",
    )

    first_result = await service.sync_telegram_user(data)
    second_result = await service.sync_telegram_user(data)
    user_count = await session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.telegram_id == data.telegram_id)
    )

    assert first_result.created is True
    assert first_result.user.id is not None
    assert second_result.created is False
    assert second_result.user.id == first_result.user.id
    assert user_count == 1


async def test_sync_persists_changed_telegram_data(session: AsyncSession) -> None:
    service = UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    )
    initial_data = TelegramUserData(
        telegram_id=9123456790,
        username="before",
        first_name="Before",
        last_name=None,
        language_code="en",
    )
    updated_data = TelegramUserData(
        telegram_id=initial_data.telegram_id,
        username="after",
        first_name="After",
        last_name="Update",
        language_code="ru",
    )

    await service.sync_telegram_user(initial_data)
    result = await service.sync_telegram_user(updated_data)
    await session.flush()

    assert result.created is False
    assert result.user.username == "after"
    assert result.user.first_name == "After"
    assert result.user.last_name == "Update"
    assert result.user.language_code == "ru"
