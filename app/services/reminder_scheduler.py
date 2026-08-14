import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.keyboards.reminders import build_reminder_notification_keyboard
from app.db.models.reminder import ReminderSetting, ReminderType
from app.repositories.diary import DiaryRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.weights import WeightRepository
from app.services.reminders import ReminderService

logger = logging.getLogger(__name__)

SCHEDULER_HEARTBEAT_JOB_ID = "system:scheduler-heartbeat"


class ReminderScheduler:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        misfire_grace_seconds: int,
    ) -> None:
        self._bot = bot
        self._session_factory = session_factory
        self._misfire_grace_seconds = misfire_grace_seconds
        self._scheduler = AsyncIOScheduler(
            timezone=UTC,
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self._last_heartbeat: datetime | None = None

    @property
    def running(self) -> bool:
        return self._scheduler.running

    @property
    def job_count(self) -> int:
        return sum(job.id.startswith("reminder:") for job in self._scheduler.get_jobs())

    @property
    def last_heartbeat(self) -> datetime | None:
        return self._last_heartbeat

    @property
    def next_job_time(self) -> datetime | None:
        next_run_times = [
            job.next_run_time
            for job in self._scheduler.get_jobs()
            if job.id.startswith("reminder:") and job.next_run_time is not None
        ]
        return min(next_run_times, default=None)

    async def start(self) -> None:
        async with self._session_factory() as session:
            records = await ReminderRepository(session).list_enabled_records()
        for record in records:
            self.schedule(record.setting, record.user.timezone)
        self._scheduler.add_job(
            self._touch_heartbeat,
            "interval",
            seconds=30,
            id=SCHEDULER_HEARTBEAT_JOB_ID,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        self._scheduler.start()
        self._touch_heartbeat()
        logger.info(
            "Reminder scheduler started with %d jobs",
            len(records),
            extra={"operation": "reminders.scheduler_start"},
        )

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        logger.info(
            "Reminder scheduler stopped",
            extra={"operation": "reminders.scheduler_stop"},
        )

    def schedule(self, setting: ReminderSetting, timezone_name: str) -> None:
        if not setting.enabled:
            self.remove(setting.user_id, setting.reminder_type)
            return
        weekdays = ",".join(
            str(day) for day in range(7) if setting.weekdays_mask & (1 << day)
        )
        trigger = CronTrigger(
            day_of_week=weekdays,
            hour=setting.time_local.hour,
            minute=setting.time_local.minute,
            timezone=ZoneInfo(timezone_name),
        )
        self._scheduler.add_job(
            self.run_job,
            trigger=trigger,
            args=(setting.id,),
            id=self.job_id(setting.user_id, setting.reminder_type),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=self._misfire_grace_seconds,
        )

    def remove(self, user_id: int, reminder_type: ReminderType) -> None:
        job = self._scheduler.get_job(self.job_id(user_id, reminder_type))
        if job is not None:
            self._scheduler.remove_job(job.id)

    def remove_user(self, user_id: int) -> None:
        for reminder_type in ReminderType:
            self.remove(user_id, reminder_type)

    async def reschedule_user_timezone(
        self,
        user_id: int,
        timezone_name: str,
    ) -> None:
        async with self._session_factory() as session:
            settings = await ReminderRepository(session).list_for_user(user_id)
        for setting in settings:
            if setting.enabled:
                self.schedule(setting, timezone_name)

    async def run_job(self, setting_id: int) -> None:
        async with self._session_factory() as session:
            service = self._service(session)
            delivery = await service.prepare_delivery(setting_id)
        if delivery is None:
            return
        try:
            await self._bot.send_message(
                delivery.telegram_id,
                delivery.text,
                reply_markup=build_reminder_notification_keyboard(
                    delivery.reminder_type
                ),
            )
        except TelegramForbiddenError:
            logger.warning(
                "Reminder disabled because Telegram access is forbidden",
                extra={
                    "operation": "reminders.forbidden",
                    "user_id": delivery.telegram_id,
                },
            )
            async with self._session_factory() as session, session.begin():
                await ReminderRepository(session).disable_by_id(setting_id)
            self.remove(delivery.user_id, delivery.reminder_type)
        except TelegramAPIError as error:
            logger.warning(
                "Reminder delivery failed",
                extra={
                    "operation": "reminders.delivery",
                    "user_id": delivery.telegram_id,
                    "exception_type": type(error).__name__,
                },
            )

    def _touch_heartbeat(self) -> None:
        self._last_heartbeat = datetime.now(UTC)

    @staticmethod
    def job_id(user_id: int, reminder_type: ReminderType) -> str:
        return f"reminder:{user_id}:{reminder_type.value}"

    @staticmethod
    def _service(session: AsyncSession) -> ReminderService:
        return ReminderService(
            ReminderRepository(session),
            WeightRepository(session),
            DiaryRepository(session),
            NutritionGoalRepository(session),
        )
