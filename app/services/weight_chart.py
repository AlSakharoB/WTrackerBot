from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from re import fullmatch
from zoneinfo import ZoneInfo

from app.exceptions import ValidationError
from app.repositories.goals import GoalRepository
from app.repositories.weights import WeightRepository

MAX_CHART_DAYS = 365
CHART_PERIODS = (7, 30, 90, 180, 365)
CHART_PERIOD_LABELS = {
    7: "7 дней",
    30: "30 дней",
    90: "90 дней",
    180: "180 дней",
    365: "1 год",
}


@dataclass(frozen=True, slots=True)
class WeightChartRange:
    date_from: date
    date_to: date
    label: str

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1


@dataclass(frozen=True, slots=True)
class WeightChartPoint:
    measured_at: datetime
    weight_kg: Decimal
    entry_id: int | None = None
    note: str | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WeightChartData:
    period: WeightChartRange
    points: tuple[WeightChartPoint, ...]
    target_weight_kg: Decimal | None

    @property
    def first(self) -> WeightChartPoint | None:
        return self.points[0] if self.points else None

    @property
    def last(self) -> WeightChartPoint | None:
        return self.points[-1] if self.points else None

    @property
    def change_kg(self) -> Decimal | None:
        if self.first is None or self.last is None:
            return None
        return self.last.weight_kg - self.first.weight_kg

    @property
    def minimum_kg(self) -> Decimal | None:
        return min((point.weight_kg for point in self.points), default=None)

    @property
    def maximum_kg(self) -> Decimal | None:
        return max((point.weight_kg for point in self.points), default=None)

    @property
    def moving_average_7d(self) -> tuple[Decimal | None, ...]:
        if not self.points:
            return ()
        window: deque[WeightChartPoint] = deque()
        total = Decimal("0")
        first_full_window = self.points[0].measured_at + timedelta(days=6)
        averages: list[Decimal | None] = []
        for point in self.points:
            earliest = point.measured_at - timedelta(days=6)
            while window and window[0].measured_at < earliest:
                total -= window.popleft().weight_kg
            window.append(point)
            total += point.weight_kg
            averages.append(
                total / len(window) if point.measured_at >= first_full_window else None
            )
        return tuple(averages)


def parse_chart_date(raw_value: str) -> date:
    value = raw_value.strip()
    try:
        if fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            return datetime.strptime(value, "%d.%m.%Y").date()
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError(
            "Введите дату в формате ДД.ММ.ГГГГ. Например: 01.08.2026"
        ) from error


def custom_chart_range(date_from: date, date_to: date) -> WeightChartRange:
    if date_to < date_from:
        raise ValidationError("Конечная дата не может быть раньше начальной.")
    days = (date_to - date_from).days + 1
    if days > MAX_CHART_DAYS:
        raise ValidationError("Период графика не может превышать 365 дней.")
    return WeightChartRange(
        date_from=date_from,
        date_to=date_to,
        label=f"{date_from:%d.%m.%Y} – {date_to:%d.%m.%Y}",
    )


def fixed_chart_range(days: int, today: date) -> WeightChartRange:
    if days not in CHART_PERIODS:
        raise ValidationError("Выберите доступный период графика.")
    return WeightChartRange(
        date_from=today - timedelta(days=days - 1),
        date_to=today,
        label=CHART_PERIOD_LABELS[days],
    )


class WeightChartService:
    def __init__(
        self,
        weight_repository: WeightRepository,
        goal_repository: GoalRepository,
    ) -> None:
        self._weights = weight_repository
        self._goals = goal_repository

    async def get_data(
        self,
        *,
        user_id: int,
        period: WeightChartRange,
        timezone_name: str,
    ) -> WeightChartData:
        custom_chart_range(period.date_from, period.date_to)
        timezone = ZoneInfo(timezone_name)
        date_from = datetime.combine(period.date_from, time.min, timezone)
        date_to_exclusive = datetime.combine(
            period.date_to + timedelta(days=1),
            time.min,
            timezone,
        )
        entries = await self._weights.list_between(
            user_id,
            date_from=date_from.astimezone(UTC),
            date_to_exclusive=date_to_exclusive.astimezone(UTC),
        )
        active_goal = await self._goals.get_active(user_id)
        points = tuple(
            WeightChartPoint(
                measured_at=entry.measured_at.astimezone(timezone),
                weight_kg=entry.weight_kg,
                entry_id=entry.id,
                note=entry.note,
                updated_at=entry.updated_at,
            )
            for entry in entries
        )
        return WeightChartData(
            period=period,
            points=points,
            target_weight_kg=(
                active_goal.target_weight_kg if active_goal is not None else None
            ),
        )
