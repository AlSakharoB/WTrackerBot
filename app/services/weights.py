from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from math import ceil
from re import fullmatch
from zoneinfo import ZoneInfo

from app.db.models.weight import WeightEntry
from app.exceptions import NotFoundError, StaleDataError, ValidationError
from app.repositories.weights import WeightRepository

WEIGHTS_PAGE_SIZE = 8
RECENT_WEIGHTS_LIMIT = 3
MIN_WEIGHT_KG = Decimal("20")
MAX_WEIGHT_KG = Decimal("500")


@dataclass(frozen=True, slots=True)
class WeightPage:
    items: list[WeightEntry]
    page: int
    pages: int
    total: int


@dataclass(frozen=True, slots=True)
class WeightSummary:
    current: WeightEntry | None
    first: WeightEntry | None
    difference_kg: Decimal | None
    recent: list[WeightEntry]


def parse_weight(raw_value: str) -> Decimal:
    normalized = raw_value.strip().replace(",", ".")
    if fullmatch(r"\d+(?:\.\d{1,2})?", normalized) is None:
        raise ValidationError("Введите вес от 20 до 500 кг. Например: 82.4")
    try:
        value = Decimal(normalized)
    except InvalidOperation as error:
        raise ValidationError("Введите вес от 20 до 500 кг. Например: 82.4") from error
    if not value.is_finite() or value < MIN_WEIGHT_KG or value > MAX_WEIGHT_KG:
        raise ValidationError("Введите вес от 20 до 500 кг. Например: 82.4")
    return value


def validate_weight(value: Decimal) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < MIN_WEIGHT_KG
        or value > MAX_WEIGHT_KG
        or value != value.quantize(Decimal("0.01"))
    ):
        raise ValidationError("Введите вес от 20 до 500 кг. Например: 82.4")


def parse_measured_at(raw_value: str, timezone_name: str) -> datetime:
    try:
        local_value = datetime.strptime(raw_value.strip(), "%d.%m.%Y %H:%M")
    except ValueError as error:
        raise ValidationError(
            "Введите дату и время в формате ДД.ММ.ГГГГ ЧЧ:ММ.\n"
            "Например: 11.08.2026 08:30"
        ) from error
    return local_value.replace(tzinfo=ZoneInfo(timezone_name))


def now_in_timezone(
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(ZoneInfo(timezone_name))


def today_morning(
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    return now_in_timezone(timezone_name, now).replace(
        hour=8,
        minute=0,
        second=0,
        microsecond=0,
    )


class WeightService:
    def __init__(self, repository: WeightRepository) -> None:
        self._repository = repository

    async def create(
        self,
        *,
        user_id: int,
        weight_kg: Decimal,
        measured_at: datetime,
        note: str | None = None,
    ) -> WeightEntry:
        validate_weight(weight_kg)
        self._validate_measured_at(measured_at)
        return await self._repository.create(
            user_id=user_id,
            weight_kg=weight_kg,
            measured_at=measured_at,
            note=note,
        )

    async def get(self, user_id: int, entry_id: int) -> WeightEntry:
        entry = await self._repository.get_by_id(entry_id, user_id)
        if entry is None:
            raise NotFoundError("Запись веса не найдена.")
        return entry

    async def get_summary(self, user_id: int) -> WeightSummary:
        current = await self._repository.get_latest(user_id)
        first = await self._repository.get_first(user_id)
        recent = await self._repository.list(
            user_id,
            limit=RECENT_WEIGHTS_LIMIT,
            offset=0,
        )
        difference = (
            current.weight_kg - first.weight_kg
            if current is not None and first is not None
            else None
        )
        return WeightSummary(
            current=current,
            first=first,
            difference_kg=difference,
            recent=recent,
        )

    async def list_page(self, user_id: int, page: int) -> WeightPage:
        total = await self._repository.count(user_id)
        pages = max(1, ceil(total / WEIGHTS_PAGE_SIZE))
        current_page = min(max(page, 1), pages)
        items = await self._repository.list(
            user_id,
            limit=WEIGHTS_PAGE_SIZE,
            offset=(current_page - 1) * WEIGHTS_PAGE_SIZE,
        )
        return WeightPage(
            items=items,
            page=current_page,
            pages=pages,
            total=total,
        )

    async def update_weight(
        self,
        user_id: int,
        entry_id: int,
        weight_kg: Decimal,
    ) -> WeightEntry:
        validate_weight(weight_kg)
        return await self._update(user_id, entry_id, {"weight_kg": weight_kg})

    async def update_measured_at(
        self,
        user_id: int,
        entry_id: int,
        measured_at: datetime,
    ) -> WeightEntry:
        self._validate_measured_at(measured_at)
        return await self._update(
            user_id,
            entry_id,
            {"measured_at": measured_at},
        )

    async def update_entry(
        self,
        user_id: int,
        entry_id: int,
        *,
        expected_updated_at: datetime,
        weight_kg: Decimal | None = None,
        measured_at: datetime | None = None,
        note: str | None = None,
        note_provided: bool = False,
    ) -> WeightEntry:
        entry = await self.get(user_id, entry_id)
        if entry.updated_at != expected_updated_at:
            raise StaleDataError(
                "Запись уже изменена. Обновите историю и повторите действие."
            )
        values: dict[str, object] = {}
        if weight_kg is not None:
            validate_weight(weight_kg)
            values["weight_kg"] = weight_kg
        if measured_at is not None:
            self._validate_measured_at(measured_at)
            values["measured_at"] = measured_at
        if note_provided:
            values["note"] = note
        if not values:
            return entry
        updated = await self._repository.update_if_current(
            entry_id,
            user_id,
            expected_updated_at,
            values,
        )
        if updated is None:
            if await self._repository.get_by_id(entry_id, user_id) is None:
                raise NotFoundError("Запись веса не найдена.")
            raise StaleDataError(
                "Запись уже изменена. Обновите историю и повторите действие."
            )
        return updated

    async def delete(self, user_id: int, entry_id: int) -> None:
        if not await self._repository.delete(entry_id, user_id):
            raise NotFoundError("Запись веса не найдена.")

    async def _update(
        self,
        user_id: int,
        entry_id: int,
        values: dict[str, object],
    ) -> WeightEntry:
        updated = await self._repository.update(entry_id, user_id, values)
        if updated is None:
            raise NotFoundError("Запись веса не найдена.")
        return updated

    @staticmethod
    def _validate_measured_at(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError("Дата и время должны содержать часовой пояс.")
