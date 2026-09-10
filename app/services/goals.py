from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from re import fullmatch

from app.db.models.goal import WeightGoal
from app.db.models.weight import WeightEntry
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.goals import GoalRepository
from app.repositories.weights import WeightRepository
from app.services.weights import validate_weight

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class GoalProgress:
    percentage: Decimal
    completed_kg: Decimal
    remaining_kg: Decimal
    achieved: bool


@dataclass(frozen=True, slots=True)
class GoalDetails:
    goal: WeightGoal
    current_weight: WeightEntry | None
    progress: GoalProgress | None


def parse_target_date(raw_value: str) -> date:
    value = raw_value.strip()
    try:
        if fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            return datetime.strptime(value, "%d.%m.%Y").date()
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError(
            "Введите дату в формате ДД.ММ.ГГГГ. Например: 15.12.2026"
        ) from error


def calculate_goal_progress(
    *,
    start_weight_kg: Decimal,
    target_weight_kg: Decimal,
    current_weight_kg: Decimal,
) -> GoalProgress:
    validate_weight(start_weight_kg)
    validate_weight(target_weight_kg)
    validate_weight(current_weight_kg)

    total_delta = target_weight_kg - start_weight_kg
    if total_delta == ZERO:
        return GoalProgress(
            percentage=ONE_HUNDRED,
            completed_kg=ZERO,
            remaining_kg=ZERO,
            achieved=True,
        )

    direction = Decimal("1") if total_delta > ZERO else Decimal("-1")
    directed_progress = (current_weight_kg - start_weight_kg) * direction
    percentage = directed_progress / abs(total_delta) * ONE_HUNDRED
    percentage = min(max(percentage, ZERO), ONE_HUNDRED)
    completed = min(max(directed_progress, ZERO), abs(total_delta))
    if percentage == ZERO:
        percentage = ZERO
    if completed == ZERO:
        completed = ZERO
    achieved = (
        current_weight_kg >= target_weight_kg
        if direction > ZERO
        else current_weight_kg <= target_weight_kg
    )
    remaining = ZERO if achieved else abs(target_weight_kg - current_weight_kg)
    return GoalProgress(
        percentage=percentage,
        completed_kg=completed,
        remaining_kg=remaining,
        achieved=achieved,
    )


class GoalService:
    def __init__(
        self,
        repository: GoalRepository,
        weight_repository: WeightRepository,
    ) -> None:
        self._repository = repository
        self._weights = weight_repository

    async def create(
        self,
        *,
        user_id: int,
        target_weight_kg: Decimal,
        target_date: date | None,
        replace_existing: bool = False,
    ) -> GoalDetails:
        validate_weight(target_weight_kg)
        current = await self._weights.get_latest(user_id)
        active = await self._repository.get_active(user_id)
        if active is not None and not replace_existing:
            raise DuplicateError("У вас уже есть активная цель.")

        values = {
            "user_id": user_id,
            "target_weight_kg": target_weight_kg,
            "target_date": target_date,
            "start_weight_kg": current.weight_kg if current is not None else None,
        }
        goal = (
            await self._repository.replace_active(**values)
            if active is not None
            else await self._repository.create(**values)
        )
        return self._build_details(goal, current)

    async def get_active(self, user_id: int) -> GoalDetails | None:
        goal = await self._repository.get_active(user_id)
        if goal is None:
            return None
        current = await self._weights.get_latest(user_id)
        if goal.start_weight_kg is None and current is not None:
            initialized = await self._repository.initialize_start_weight(
                goal_id=goal.id,
                user_id=user_id,
                start_weight_kg=current.weight_kg,
            )
            goal = initialized or await self._repository.get_active(user_id)
            if goal is None:
                return None
        return self._build_details(goal, current)

    async def get_current_weight(self, user_id: int) -> WeightEntry | None:
        return await self._weights.get_latest(user_id)

    async def complete(self, user_id: int, goal_id: int) -> WeightGoal:
        goal = await self._repository.complete(goal_id, user_id)
        if goal is None:
            raise NotFoundError("Активная цель не найдена.")
        return goal

    async def cancel(self, user_id: int, goal_id: int) -> WeightGoal:
        goal = await self._repository.cancel(goal_id, user_id)
        if goal is None:
            raise NotFoundError("Активная цель не найдена.")
        return goal

    @staticmethod
    def _build_details(
        goal: WeightGoal,
        current: WeightEntry | None,
    ) -> GoalDetails:
        progress = (
            calculate_goal_progress(
                start_weight_kg=goal.start_weight_kg,
                target_weight_kg=goal.target_weight_kg,
                current_weight_kg=current.weight_kg,
            )
            if goal.start_weight_kg is not None and current is not None
            else None
        )
        return GoalDetails(goal=goal, current_weight=current, progress=progress)
