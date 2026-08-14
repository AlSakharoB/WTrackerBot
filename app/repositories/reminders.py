from dataclasses import dataclass
from datetime import time

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.reminder import ReminderSetting, ReminderType
from app.db.models.user import User


@dataclass(frozen=True, slots=True)
class ReminderRecord:
    setting: ReminderSetting
    user: User


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        user_id: int,
        reminder_type: ReminderType,
    ) -> ReminderSetting | None:
        return await self._session.scalar(
            select(ReminderSetting).where(
                ReminderSetting.user_id == user_id,
                ReminderSetting.reminder_type == reminder_type,
            )
        )

    async def list_for_user(self, user_id: int) -> list[ReminderSetting]:
        statement = (
            select(ReminderSetting)
            .where(ReminderSetting.user_id == user_id)
            .order_by(ReminderSetting.reminder_type)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_enabled_records(self) -> list[ReminderRecord]:
        statement = (
            select(ReminderSetting, User)
            .join(User, User.id == ReminderSetting.user_id)
            .where(ReminderSetting.enabled.is_(True))
            .order_by(ReminderSetting.id)
        )
        return [
            ReminderRecord(setting=setting, user=user)
            for setting, user in (await self._session.execute(statement)).all()
        ]

    async def get_enabled_record(self, setting_id: int) -> ReminderRecord | None:
        statement = (
            select(ReminderSetting, User)
            .join(User, User.id == ReminderSetting.user_id)
            .where(
                ReminderSetting.id == setting_id,
                ReminderSetting.enabled.is_(True),
            )
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            return None
        setting, user = row
        return ReminderRecord(setting=setting, user=user)

    async def upsert(
        self,
        *,
        user_id: int,
        reminder_type: ReminderType,
        time_local: time,
        weekdays_mask: int,
    ) -> ReminderSetting:
        statement = (
            insert(ReminderSetting)
            .values(
                user_id=user_id,
                reminder_type=reminder_type,
                enabled=True,
                time_local=time_local,
                weekdays_mask=weekdays_mask,
            )
            .on_conflict_do_update(
                constraint="uq_reminder_settings_user_id_reminder_type",
                set_={
                    "enabled": True,
                    "time_local": time_local,
                    "weekdays_mask": weekdays_mask,
                },
            )
            .returning(ReminderSetting)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def disable(
        self,
        user_id: int,
        reminder_type: ReminderType,
    ) -> ReminderSetting | None:
        statement = (
            update(ReminderSetting)
            .where(
                ReminderSetting.user_id == user_id,
                ReminderSetting.reminder_type == reminder_type,
            )
            .values(enabled=False)
            .returning(ReminderSetting)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def disable_by_id(self, setting_id: int) -> None:
        await self._session.execute(
            update(ReminderSetting)
            .where(ReminderSetting.id == setting_id)
            .values(enabled=False)
        )

    async def delete_for_user(self, user_id: int) -> None:
        await self._session.execute(
            delete(ReminderSetting).where(ReminderSetting.user_id == user_id)
        )
