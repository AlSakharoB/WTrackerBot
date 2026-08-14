from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.users import UserRepository
from app.services.settings import UserSettingsService
from app.services.users import TelegramUserData, UserService
from app.user_settings import AfterFoodAddAction, NumberFormat
from app.utils.datetime import local_today


async def create_user(session: AsyncSession, telegram_id: int):
    return (
        await UserService(
            UserRepository(session),
            default_timezone="Europe/Moscow",
        ).sync_telegram_user(
            TelegramUserData(
                telegram_id=telegram_id,
                username=None,
                first_name="Settings Test",
                last_name=None,
                language_code="ru",
            )
        )
    ).user


async def test_settings_persist_and_are_isolated_by_user(
    session: AsyncSession,
) -> None:
    first = await create_user(session, 9770000001)
    second = await create_user(session, 9770000002)
    first_telegram_id = first.telegram_id
    second_telegram_id = second.telegram_id
    service = UserSettingsService(UserRepository(session))

    await service.set_timezone(first.id, "Europe/London")
    await service.set_number_format(first.id, NumberFormat.TWO_DECIMALS)
    await service.set_after_food_add_action(first.id, AfterFoodAddAction.STAY)
    await session.flush()
    session.expire_all()

    persisted_first = await UserRepository(session).get_by_telegram_id(
        first_telegram_id
    )
    persisted_second = await UserRepository(session).get_by_telegram_id(
        second_telegram_id
    )

    assert persisted_first is not None
    assert persisted_first.timezone == "Europe/London"
    assert persisted_first.number_format == NumberFormat.TWO_DECIMALS.value
    assert persisted_first.after_food_add_action == AfterFoodAddAction.STAY.value
    assert persisted_second is not None
    assert persisted_second.timezone == "Europe/Moscow"
    assert persisted_second.number_format == NumberFormat.AUTOMATIC.value
    assert persisted_second.after_food_add_action == AfterFoodAddAction.OPEN_TODAY.value


async def test_today_uses_persisted_user_timezone(session: AsyncSession) -> None:
    first = await create_user(session, 9770000003)
    second = await create_user(session, 9770000004)
    service = UserSettingsService(UserRepository(session))
    almaty_user = await service.set_timezone(first.id, "Asia/Almaty")
    london_user = await service.set_timezone(second.id, "Europe/London")
    now = datetime(2026, 8, 14, 19, 30, tzinfo=UTC)

    assert local_today(almaty_user.timezone, now).isoformat() == "2026-08-15"
    assert local_today(london_user.timezone, now).isoformat() == "2026-08-14"
