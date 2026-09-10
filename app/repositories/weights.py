from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.weight import WeightEntry


class WeightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        weight_kg: Decimal,
        measured_at: datetime,
        note: str | None = None,
    ) -> WeightEntry:
        statement = (
            insert(WeightEntry)
            .values(
                user_id=user_id,
                weight_kg=weight_kg,
                measured_at=measured_at,
                note=note,
            )
            .returning(WeightEntry)
        )
        return (await self._session.scalars(statement)).one()

    async def get_by_id(self, entry_id: int, user_id: int) -> WeightEntry | None:
        return await self._session.scalar(
            select(WeightEntry).where(
                WeightEntry.id == entry_id,
                WeightEntry.user_id == user_id,
            )
        )

    async def count(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(WeightEntry)
            .where(WeightEntry.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)

    async def list(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[WeightEntry]:
        statement = (
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(WeightEntry.measured_at.desc(), WeightEntry.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def list_between(
        self,
        user_id: int,
        *,
        date_from: datetime,
        date_to_exclusive: datetime,
    ) -> list[WeightEntry]:
        statement = (
            select(WeightEntry)
            .where(
                WeightEntry.user_id == user_id,
                WeightEntry.measured_at >= date_from,
                WeightEntry.measured_at < date_to_exclusive,
            )
            .order_by(WeightEntry.measured_at, WeightEntry.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def exists_between(
        self,
        user_id: int,
        *,
        date_from: datetime,
        date_to_exclusive: datetime,
    ) -> bool:
        statement = (
            select(WeightEntry.id)
            .where(
                WeightEntry.user_id == user_id,
                WeightEntry.measured_at >= date_from,
                WeightEntry.measured_at < date_to_exclusive,
            )
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    async def get_latest(self, user_id: int) -> WeightEntry | None:
        statement = (
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(WeightEntry.measured_at.desc(), WeightEntry.id.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def get_first(self, user_id: int) -> WeightEntry | None:
        statement = (
            select(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .order_by(WeightEntry.measured_at, WeightEntry.id)
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def update(
        self,
        entry_id: int,
        user_id: int,
        values: dict[str, Any],
    ) -> WeightEntry | None:
        statement = (
            update(WeightEntry)
            .where(
                WeightEntry.id == entry_id,
                WeightEntry.user_id == user_id,
            )
            .values(**values)
            .returning(WeightEntry)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def update_if_current(
        self,
        entry_id: int,
        user_id: int,
        expected_updated_at: datetime,
        values: dict[str, Any],
    ) -> WeightEntry | None:
        statement = (
            update(WeightEntry)
            .where(
                WeightEntry.id == entry_id,
                WeightEntry.user_id == user_id,
                WeightEntry.updated_at == expected_updated_at,
            )
            .values(**values)
            .returning(WeightEntry)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def delete(self, entry_id: int, user_id: int) -> bool:
        statement = (
            delete(WeightEntry)
            .where(
                WeightEntry.id == entry_id,
                WeightEntry.user_id == user_id,
            )
            .returning(WeightEntry.id)
        )
        return await self._session.scalar(statement) is not None
