from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.goal import GoalStatus, WeightGoal
from app.exceptions import DuplicateError


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        target_weight_kg: Decimal,
        target_date: date | None,
        start_weight_kg: Decimal | None,
    ) -> WeightGoal:
        try:
            async with self._session.begin_nested():
                return await self._insert(
                    user_id=user_id,
                    target_weight_kg=target_weight_kg,
                    target_date=target_date,
                    start_weight_kg=start_weight_kg,
                )
        except IntegrityError as error:
            raise DuplicateError("У вас уже есть активная цель.") from error

    async def replace_active(
        self,
        *,
        user_id: int,
        target_weight_kg: Decimal,
        target_date: date | None,
        start_weight_kg: Decimal | None,
    ) -> WeightGoal:
        try:
            async with self._session.begin_nested():
                await self._session.execute(
                    update(WeightGoal)
                    .where(
                        WeightGoal.user_id == user_id,
                        WeightGoal.status == GoalStatus.ACTIVE,
                    )
                    .values(status=GoalStatus.CANCELLED, completed_at=None)
                )
                return await self._insert(
                    user_id=user_id,
                    target_weight_kg=target_weight_kg,
                    target_date=target_date,
                    start_weight_kg=start_weight_kg,
                )
        except IntegrityError as error:
            raise DuplicateError("Не удалось заменить активную цель.") from error

    async def get_active(self, user_id: int) -> WeightGoal | None:
        statement = (
            select(WeightGoal)
            .where(
                WeightGoal.user_id == user_id,
                WeightGoal.status == GoalStatus.ACTIVE,
            )
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def get_by_id(self, goal_id: int, user_id: int) -> WeightGoal | None:
        statement = select(WeightGoal).where(
            WeightGoal.id == goal_id,
            WeightGoal.user_id == user_id,
        )
        return await self._session.scalar(statement)

    async def initialize_start_weight(
        self,
        *,
        goal_id: int,
        user_id: int,
        start_weight_kg: Decimal,
    ) -> WeightGoal | None:
        statement = (
            update(WeightGoal)
            .where(
                WeightGoal.id == goal_id,
                WeightGoal.user_id == user_id,
                WeightGoal.status == GoalStatus.ACTIVE,
                WeightGoal.start_weight_kg.is_(None),
            )
            .values(start_weight_kg=start_weight_kg)
            .returning(WeightGoal)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def complete(self, goal_id: int, user_id: int) -> WeightGoal | None:
        statement = (
            update(WeightGoal)
            .where(
                WeightGoal.id == goal_id,
                WeightGoal.user_id == user_id,
                WeightGoal.status == GoalStatus.ACTIVE,
            )
            .values(status=GoalStatus.COMPLETED, completed_at=func.now())
            .returning(WeightGoal)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def cancel(self, goal_id: int, user_id: int) -> WeightGoal | None:
        statement = (
            update(WeightGoal)
            .where(
                WeightGoal.id == goal_id,
                WeightGoal.user_id == user_id,
                WeightGoal.status == GoalStatus.ACTIVE,
            )
            .values(status=GoalStatus.CANCELLED, completed_at=None)
            .returning(WeightGoal)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def _insert(
        self,
        *,
        user_id: int,
        target_weight_kg: Decimal,
        target_date: date | None,
        start_weight_kg: Decimal | None,
    ) -> WeightGoal:
        statement = (
            insert(WeightGoal)
            .values(
                user_id=user_id,
                target_weight_kg=target_weight_kg,
                target_date=target_date,
                start_weight_kg=start_weight_kg,
                status=GoalStatus.ACTIVE,
            )
            .returning(WeightGoal)
        )
        return (await self._session.scalars(statement)).one()
