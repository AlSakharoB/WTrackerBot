from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from re import fullmatch
from zoneinfo import ZoneInfo

from app.db.models.reminder import ReminderSetting, ReminderType
from app.exceptions import NotFoundError, ValidationError
from app.repositories.diary import DiaryRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.weights import WeightRepository
from app.services.nutrition import NutritionService, NutritionValues
from app.utils.decimal import format_decimal

WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
ALL_WEEKDAYS_MASK = 0b1111111


@dataclass(frozen=True, slots=True)
class ReminderDelivery:
    setting_id: int
    telegram_id: int
    user_id: int
    reminder_type: ReminderType
    text: str


def parse_reminder_time(raw_value: str) -> time:
    value = raw_value.strip()
    match = fullmatch(r"([0-9]{1,2}):([0-9]{2})", value)
    if match is None:
        raise ValidationError("Введите время в формате Ч:ММ. Например: 8:00")
    try:
        parsed = time(hour=int(match.group(1)), minute=int(match.group(2)))
    except ValueError as error:
        raise ValidationError("Введите время в формате Ч:ММ. Например: 8:00") from error
    return parsed


def validate_weekdays_mask(value: int) -> None:
    if not isinstance(value, int) or value < 1 or value > ALL_WEEKDAYS_MASK:
        raise ValidationError("Выберите хотя бы один день недели.")


def toggle_weekday(mask: int, weekday: int) -> int:
    if weekday < 0 or weekday > 6:
        raise ValidationError("Неизвестный день недели.")
    return mask ^ (1 << weekday)


def format_weekdays(mask: int) -> str:
    validate_weekdays_mask(mask)
    return ", ".join(
        label for index, label in enumerate(WEEKDAY_LABELS) if mask & (1 << index)
    )


class ReminderService:
    def __init__(
        self,
        repository: ReminderRepository,
        weight_repository: WeightRepository,
        diary_repository: DiaryRepository,
        nutrition_goal_repository: NutritionGoalRepository,
    ) -> None:
        self._repository = repository
        self._weights = weight_repository
        self._diary = diary_repository
        self._nutrition_goals = nutrition_goal_repository

    async def list_for_user(self, user_id: int) -> list[ReminderSetting]:
        return await self._repository.list_for_user(user_id)

    async def configure(
        self,
        *,
        user_id: int,
        reminder_type: ReminderType,
        time_local: time,
        weekdays_mask: int,
    ) -> ReminderSetting:
        validate_weekdays_mask(weekdays_mask)
        if time_local.tzinfo is not None:
            raise ValidationError("Время напоминания должно быть локальным.")
        return await self._repository.upsert(
            user_id=user_id,
            reminder_type=reminder_type,
            time_local=time_local.replace(second=0, microsecond=0),
            weekdays_mask=weekdays_mask,
        )

    async def disable(
        self,
        user_id: int,
        reminder_type: ReminderType,
    ) -> ReminderSetting | None:
        return await self._repository.disable(user_id, reminder_type)

    async def update(
        self,
        setting_id: int,
        user_id: int,
        *,
        enabled: bool | None = None,
        time_local: time | None = None,
        weekdays_mask: int | None = None,
    ) -> ReminderSetting:
        current = await self._repository.get_by_id(setting_id, user_id)
        if current is None:
            raise NotFoundError("Напоминание не найдено.")
        if enabled is False:
            disabled = await self.disable(user_id, current.reminder_type)
            if disabled is None:
                raise NotFoundError("Напоминание не найдено.")
            return disabled
        configured = await self.configure(
            user_id=user_id,
            reminder_type=current.reminder_type,
            time_local=time_local or current.time_local,
            weekdays_mask=(
                weekdays_mask if weekdays_mask is not None else current.weekdays_mask
            ),
        )
        if not current.enabled and enabled is not True:
            disabled = await self.disable(user_id, current.reminder_type)
            if disabled is None:
                raise NotFoundError("Напоминание не найдено.")
            return disabled
        return configured

    async def delete(self, setting_id: int, user_id: int) -> None:
        if not await self._repository.delete(setting_id, user_id):
            raise NotFoundError("Напоминание не найдено.")

    async def prepare_delivery(
        self,
        setting_id: int,
        *,
        now: datetime | None = None,
    ) -> ReminderDelivery | None:
        record = await self._repository.get_enabled_record(setting_id)
        if record is None:
            return None
        setting = record.setting
        user = record.user
        timezone = ZoneInfo(user.timezone)
        current = (now or datetime.now(UTC)).astimezone(timezone)
        if not setting.weekdays_mask & (1 << current.weekday()):
            return None

        if setting.reminder_type is ReminderType.WEIGH_IN:
            if await self._has_weight_today(user.id, current.date(), timezone):
                return None
            text = (
                "⚖️ <b>Пора взвеситься</b>\n\n"
                "Если сегодня планировали измерение,\n"
                "можно добавить вес одной кнопкой."
            )
        else:
            text = await self._nutrition_text(user.id, current.date())
        return ReminderDelivery(
            setting_id=setting.id,
            telegram_id=user.telegram_id,
            user_id=user.id,
            reminder_type=setting.reminder_type,
            text=text,
        )

    async def _has_weight_today(
        self,
        user_id: int,
        today: date,
        timezone: ZoneInfo,
    ) -> bool:
        date_from = datetime.combine(today, time.min, timezone).astimezone(UTC)
        date_to = datetime.combine(
            today + timedelta(days=1),
            time.min,
            timezone,
        ).astimezone(UTC)
        return await self._weights.exists_between(
            user_id,
            date_from=date_from,
            date_to_exclusive=date_to,
        )

    async def _nutrition_text(self, user_id: int, today: date) -> str:
        entries = await self._diary.list_by_date(user_id, today)
        totals = NutritionService.sum_nutrition(
            NutritionValues(
                kcal=entry.kcal_snapshot,
                protein=entry.protein_snapshot,
                fat=entry.fat_snapshot,
                carbs=entry.carbs_snapshot,
            )
            for entry in entries
        )
        goal = await self._nutrition_goals.get_for_date(user_id, today)
        if goal is None:
            return (
                "🥗 <b>Напоминание о дневнике</b>\n\n"
                "Можно проверить,\nвсё ли внесено в рацион."
            )

        values = (
            ("🔥", totals.kcal, goal.kcal_target),
            ("🥩", totals.protein, goal.protein_target_g),
            ("🥑", totals.fat, goal.fat_target_g),
            ("🍞", totals.carbs, goal.carbs_target_g),
        )
        lines = ["🥗 <b>Дневной рацион</b>", ""]
        lines.extend(
            f"{icon} {format_decimal(current)} / {format_decimal(target)}"
            for icon, current, target in values
            if target is not None
        )
        return "\n".join(lines)
