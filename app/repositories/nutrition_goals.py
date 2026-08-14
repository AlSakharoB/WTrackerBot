from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.user import User


class NutritionGoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_user(self, user_id: int) -> bool:
        statement = select(User.id).where(User.id == user_id).with_for_update()
        return await self._session.scalar(statement) is not None

    async def get_for_date(
        self,
        user_id: int,
        target_date: date,
    ) -> NutritionGoal | None:
        statement = select(NutritionGoal).where(
            NutritionGoal.user_id == user_id,
            NutritionGoal.effective_from <= target_date,
            (NutritionGoal.effective_to.is_(None))
            | (NutritionGoal.effective_to >= target_date),
        )
        return await self._session.scalar(statement)

    async def get_open(self, user_id: int) -> NutritionGoal | None:
        statement = select(NutritionGoal).where(
            NutritionGoal.user_id == user_id,
            NutritionGoal.effective_to.is_(None),
        )
        return await self._session.scalar(statement)

    async def get_by_effective_from(
        self,
        user_id: int,
        effective_from: date,
    ) -> NutritionGoal | None:
        statement = select(NutritionGoal).where(
            NutritionGoal.user_id == user_id,
            NutritionGoal.effective_from == effective_from,
        )
        return await self._session.scalar(statement)

    async def get_latest_before(
        self,
        user_id: int,
        effective_from: date,
    ) -> NutritionGoal | None:
        statement = (
            select(NutritionGoal)
            .where(
                NutritionGoal.user_id == user_id,
                NutritionGoal.effective_from < effective_from,
            )
            .order_by(NutritionGoal.effective_from.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def create(
        self,
        *,
        user_id: int,
        kcal_target: Decimal | None,
        protein_target_g: Decimal | None,
        fat_target_g: Decimal | None,
        carbs_target_g: Decimal | None,
        effective_from: date,
    ) -> NutritionGoal:
        statement = (
            insert(NutritionGoal)
            .values(
                user_id=user_id,
                kcal_target=kcal_target,
                protein_target_g=protein_target_g,
                fat_target_g=fat_target_g,
                carbs_target_g=carbs_target_g,
                effective_from=effective_from,
            )
            .returning(NutritionGoal)
        )
        return (await self._session.scalars(statement)).one()

    async def replace(
        self,
        goal_id: int,
        user_id: int,
        *,
        kcal_target: Decimal | None,
        protein_target_g: Decimal | None,
        fat_target_g: Decimal | None,
        carbs_target_g: Decimal | None,
    ) -> NutritionGoal | None:
        statement = (
            update(NutritionGoal)
            .where(
                NutritionGoal.id == goal_id,
                NutritionGoal.user_id == user_id,
            )
            .values(
                kcal_target=kcal_target,
                protein_target_g=protein_target_g,
                fat_target_g=fat_target_g,
                carbs_target_g=carbs_target_g,
                effective_to=None,
            )
            .returning(NutritionGoal)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def close(self, goal_id: int, user_id: int, effective_to: date) -> None:
        await self._session.execute(
            update(NutritionGoal)
            .where(
                NutritionGoal.id == goal_id,
                NutritionGoal.user_id == user_id,
            )
            .values(effective_to=effective_to)
        )

    async def delete_starting_after(self, user_id: int, target_date: date) -> None:
        await self._session.execute(
            delete(NutritionGoal).where(
                NutritionGoal.user_id == user_id,
                NutritionGoal.effective_from > target_date,
            )
        )

    async def delete(self, goal_id: int, user_id: int) -> None:
        await self._session.execute(
            delete(NutritionGoal).where(
                NutritionGoal.id == goal_id,
                NutritionGoal.user_id == user_id,
            )
        )
