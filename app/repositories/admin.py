from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DiaryEntry,
    Dish,
    GoalStatus,
    Ingredient,
    User,
    WeightEntry,
    WeightGoal,
)


@dataclass(frozen=True, slots=True)
class AdminUserStats:
    total: int
    new_today: int
    new_last_7_days: int


@dataclass(frozen=True, slots=True)
class AdminEntityStats:
    ingredients: int
    dishes: int
    diary_entries: int
    weight_entries: int
    active_weight_goals: int


@dataclass(frozen=True, slots=True)
class AdminDatabaseInfo:
    postgresql_version: str
    database_size: str


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_stats(
        self,
        now: datetime | None = None,
    ) -> AdminUserStats:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        else:
            current = current.astimezone(UTC)
        today_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = current - timedelta(days=7)
        statement = select(
            func.count(User.id),
            func.count(User.id).filter(User.created_at >= today_start),
            func.count(User.id).filter(User.created_at >= week_start),
        )
        total, new_today, new_last_7_days = (
            await self._session.execute(statement)
        ).one()
        return AdminUserStats(
            total=int(total),
            new_today=int(new_today),
            new_last_7_days=int(new_last_7_days),
        )

    async def get_entity_stats(self) -> AdminEntityStats:
        statement = select(
            select(func.count(Ingredient.id)).scalar_subquery(),
            select(func.count(Dish.id)).scalar_subquery(),
            select(func.count(DiaryEntry.id)).scalar_subquery(),
            select(func.count(WeightEntry.id)).scalar_subquery(),
            select(func.count(WeightGoal.id))
            .where(WeightGoal.status == GoalStatus.ACTIVE)
            .scalar_subquery(),
        )
        ingredients, dishes, diary_entries, weight_entries, active_goals = (
            await self._session.execute(statement)
        ).one()
        return AdminEntityStats(
            ingredients=int(ingredients),
            dishes=int(dishes),
            diary_entries=int(diary_entries),
            weight_entries=int(weight_entries),
            active_weight_goals=int(active_goals),
        )

    async def get_database_info(self) -> AdminDatabaseInfo:
        statement = select(
            func.current_setting("server_version"),
            func.pg_size_pretty(func.pg_database_size(func.current_database())),
        )
        postgresql_version, database_size = (
            await self._session.execute(statement)
        ).one()
        return AdminDatabaseInfo(
            postgresql_version=str(postgresql_version),
            database_size=str(database_size),
        )
