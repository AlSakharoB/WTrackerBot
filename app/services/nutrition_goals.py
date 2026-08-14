from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from re import fullmatch

from app.db.models.nutrition_goal import NutritionGoal
from app.exceptions import NotFoundError, ValidationError
from app.repositories.nutrition_goals import NutritionGoalRepository

TARGET_LIMITS = {
    "kcal_target": (Decimal("10000"), "калорий"),
    "protein_target_g": (Decimal("1000"), "белков"),
    "fat_target_g": (Decimal("1000"), "жиров"),
    "carbs_target_g": (Decimal("2000"), "углеводов"),
}


@dataclass(frozen=True, slots=True)
class NutritionGoalData:
    kcal_target: Decimal | None
    protein_target_g: Decimal | None
    fat_target_g: Decimal | None
    carbs_target_g: Decimal | None


@dataclass(frozen=True, slots=True)
class NutritionTargetProgress:
    consumed: Decimal
    target: Decimal
    percentage: Decimal
    excess: Decimal


def calculate_target_progress(
    consumed: Decimal,
    target: Decimal,
) -> NutritionTargetProgress:
    if not consumed.is_finite() or consumed < 0:
        raise ValueError("Consumed value must be finite and non-negative")
    if not target.is_finite() or target <= 0:
        raise ValueError("Target must be finite and positive")
    return NutritionTargetProgress(
        consumed=consumed,
        target=target,
        percentage=consumed / target * Decimal("100"),
        excess=max(consumed - target, Decimal("0")),
    )


def parse_nutrition_target(field: str, raw_value: str) -> Decimal:
    if field not in TARGET_LIMITS:
        raise ValueError(f"Unknown nutrition target field: {field}")
    maximum, label = TARGET_LIMITS[field]
    normalized = raw_value.strip().replace(",", ".")
    if fullmatch(r"\d+(?:\.\d{1,2})?", normalized) is None:
        raise ValidationError(f"Введите целевое количество {label} больше 0.")
    try:
        value = Decimal(normalized)
    except InvalidOperation as error:
        raise ValidationError(
            f"Введите целевое количество {label} больше 0."
        ) from error
    if not value.is_finite() or value <= 0 or value > maximum:
        raise ValidationError(f"Значение должно быть больше 0 и не больше {maximum:g}.")
    return value


def validate_nutrition_goal(data: NutritionGoalData) -> None:
    values = {
        "kcal_target": data.kcal_target,
        "protein_target_g": data.protein_target_g,
        "fat_target_g": data.fat_target_g,
        "carbs_target_g": data.carbs_target_g,
    }
    if all(value is None for value in values.values()):
        raise ValidationError("Укажите хотя бы одну цель КБЖУ.")
    for field, value in values.items():
        if value is not None:
            parse_nutrition_target(field, str(value))


class NutritionGoalService:
    def __init__(self, repository: NutritionGoalRepository) -> None:
        self._repository = repository

    async def get_for_date(
        self,
        user_id: int,
        target_date: date,
    ) -> NutritionGoal | None:
        return await self._repository.get_for_date(user_id, target_date)

    async def get_open(self, user_id: int) -> NutritionGoal | None:
        return await self._repository.get_open(user_id)

    async def set_goal(
        self,
        user_id: int,
        data: NutritionGoalData,
        effective_from: date,
    ) -> NutritionGoal:
        validate_nutrition_goal(data)
        if not await self._repository.lock_user(user_id):
            raise NotFoundError("Пользователь не найден.")

        await self._repository.delete_starting_after(user_id, effective_from)
        same_day = await self._repository.get_by_effective_from(
            user_id,
            effective_from,
        )
        if same_day is not None:
            updated = await self._repository.replace(
                same_day.id,
                user_id,
                **self._values(data),
            )
            if updated is None:
                raise NotFoundError("Цель КБЖУ не найдена.")
            return updated

        previous = await self._repository.get_latest_before(user_id, effective_from)
        if previous is not None and (
            previous.effective_to is None or previous.effective_to >= effective_from
        ):
            await self._repository.close(
                previous.id,
                user_id,
                effective_from - timedelta(days=1),
            )
        return await self._repository.create(
            user_id=user_id,
            effective_from=effective_from,
            **self._values(data),
        )

    async def disable(
        self,
        user_id: int,
        goal_id: int,
        effective_date: date,
    ) -> None:
        if not await self._repository.lock_user(user_id):
            raise NotFoundError("Пользователь не найден.")
        open_goal = await self._repository.get_open(user_id)
        if open_goal is None or open_goal.id != goal_id:
            raise NotFoundError("Цель КБЖУ уже изменена или отключена.")

        await self._repository.delete_starting_after(user_id, effective_date)
        current = await self._repository.get_for_date(user_id, effective_date)
        if current is None:
            return
        if current.effective_from == effective_date:
            await self._repository.delete(current.id, user_id)
        else:
            await self._repository.close(
                current.id,
                user_id,
                effective_date - timedelta(days=1),
            )

    @staticmethod
    def _values(data: NutritionGoalData) -> dict[str, Decimal | None]:
        return {
            "kcal_target": data.kcal_target,
            "protein_target_g": data.protein_target_g,
            "fat_target_g": data.fat_target_g,
            "carbs_target_g": data.carbs_target_g,
        }
