from datetime import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reminder import ReminderSetting, ReminderType
from app.repositories.diary import DiaryRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.users import UserRepository
from app.repositories.weights import WeightRepository
from app.services.reminders import ReminderService
from app.services.users import TelegramUserData, UserService


async def create_user(session: AsyncSession, telegram_id: int):
    return (
        await UserService(
            UserRepository(session),
            default_timezone="Europe/Moscow",
        ).sync_telegram_user(
            TelegramUserData(
                telegram_id=telegram_id,
                username=None,
                first_name="Reminder Test",
                last_name=None,
                language_code="ru",
            )
        )
    ).user


def reminder_service(session: AsyncSession) -> ReminderService:
    return ReminderService(
        ReminderRepository(session),
        WeightRepository(session),
        DiaryRepository(session),
        NutritionGoalRepository(session),
    )


async def test_reminders_persist_restart_and_are_isolated(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, 9930000001)
    other = await create_user(session, 9930000002)
    owner_id = owner.id
    other_id = other.id
    service = reminder_service(session)

    assert await service.list_for_user(owner_id) == []
    weigh = await service.configure(
        user_id=owner_id,
        reminder_type=ReminderType.WEIGH_IN,
        time_local=time(8, 0),
        weekdays_mask=0b0010101,
    )
    await service.configure(
        user_id=owner_id,
        reminder_type=ReminderType.NUTRITION,
        time_local=time(20, 30),
        weekdays_mask=0b1111111,
    )
    await service.configure(
        user_id=other_id,
        reminder_type=ReminderType.WEIGH_IN,
        time_local=time(9, 0),
        weekdays_mask=0b0000010,
    )
    updated = await service.configure(
        user_id=owner_id,
        reminder_type=ReminderType.WEIGH_IN,
        time_local=time(7, 45),
        weekdays_mask=0b0000001,
    )

    assert updated.id == weigh.id
    assert updated.time_local == time(7, 45)
    assert len(await service.list_for_user(owner_id)) == 2
    assert len(await service.list_for_user(other_id)) == 1

    await session.flush()
    session.expire_all()
    restored = await reminder_service(session).list_for_user(owner_id)
    assert len(restored) == 2
    assert all(setting.enabled for setting in restored)

    await reminder_service(session).disable(owner_id, ReminderType.WEIGH_IN)
    enabled_records = await ReminderRepository(session).list_enabled_records()
    enabled_pairs = {
        (record.user.id, record.setting.reminder_type) for record in enabled_records
    }
    assert (owner_id, ReminderType.WEIGH_IN) not in enabled_pairs
    assert (owner_id, ReminderType.NUTRITION) in enabled_pairs
    assert (other_id, ReminderType.WEIGH_IN) in enabled_pairs

    count = await session.scalar(select(func.count(ReminderSetting.id)))
    assert count == 3
