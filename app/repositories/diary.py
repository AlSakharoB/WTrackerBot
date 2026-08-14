from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType


class DiaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        entry_date: date,
        entry_type: DiaryEntryType,
        ingredient_id: int | None,
        dish_id: int | None,
        source_name: str,
        grams: Decimal,
        meal_type: MealType,
        kcal_snapshot: Decimal,
        protein_snapshot: Decimal,
        fat_snapshot: Decimal,
        carbs_snapshot: Decimal,
    ) -> DiaryEntry:
        statement = (
            insert(DiaryEntry)
            .values(
                user_id=user_id,
                entry_date=entry_date,
                entry_type=entry_type,
                ingredient_id=ingredient_id,
                dish_id=dish_id,
                source_name=source_name,
                grams=grams,
                meal_type=meal_type,
                kcal_snapshot=kcal_snapshot,
                protein_snapshot=protein_snapshot,
                fat_snapshot=fat_snapshot,
                carbs_snapshot=carbs_snapshot,
            )
            .returning(DiaryEntry)
        )
        return (await self._session.scalars(statement)).one()

    async def get_by_id(self, entry_id: int, user_id: int) -> DiaryEntry | None:
        return await self._session.scalar(
            select(DiaryEntry).where(
                DiaryEntry.id == entry_id,
                DiaryEntry.user_id == user_id,
            )
        )

    async def list_by_date(
        self,
        user_id: int,
        entry_date: date,
    ) -> list[DiaryEntry]:
        meal_order = case(
            (DiaryEntry.meal_type == MealType.BREAKFAST, 1),
            (DiaryEntry.meal_type == MealType.LUNCH, 2),
            (DiaryEntry.meal_type == MealType.DINNER, 3),
            (DiaryEntry.meal_type == MealType.SNACK, 4),
            else_=5,
        )
        statement = (
            select(DiaryEntry)
            .where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == entry_date,
            )
            .order_by(meal_order, DiaryEntry.created_at, DiaryEntry.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def count_by_date(self, user_id: int, entry_date: date) -> int:
        statement = (
            select(func.count())
            .select_from(DiaryEntry)
            .where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == entry_date,
            )
        )
        return int(await self._session.scalar(statement) or 0)

    async def list_by_date_page(
        self,
        user_id: int,
        entry_date: date,
        *,
        limit: int,
        offset: int,
    ) -> list[DiaryEntry]:
        meal_order = case(
            (DiaryEntry.meal_type == MealType.BREAKFAST, 1),
            (DiaryEntry.meal_type == MealType.LUNCH, 2),
            (DiaryEntry.meal_type == MealType.DINNER, 3),
            (DiaryEntry.meal_type == MealType.SNACK, 4),
            else_=5,
        )
        statement = (
            select(DiaryEntry)
            .where(
                DiaryEntry.user_id == user_id,
                DiaryEntry.entry_date == entry_date,
            )
            .order_by(meal_order, DiaryEntry.created_at, DiaryEntry.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def update(
        self,
        entry_id: int,
        user_id: int,
        values: dict[str, Any],
    ) -> DiaryEntry | None:
        statement = (
            update(DiaryEntry)
            .where(
                DiaryEntry.id == entry_id,
                DiaryEntry.user_id == user_id,
            )
            .values(**values)
            .returning(DiaryEntry)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def delete(self, entry_id: int, user_id: int) -> bool:
        statement = (
            delete(DiaryEntry)
            .where(
                DiaryEntry.id == entry_id,
                DiaryEntry.user_id == user_id,
            )
            .returning(DiaryEntry.id)
        )
        return await self._session.scalar(statement) is not None
