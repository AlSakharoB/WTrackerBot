from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.external_product import (
    ExternalProductCache,
    IngredientExternalSource,
)
from app.db.models.ingredient import Ingredient


class ExternalProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cached(
        self, provider: str, barcode: str, now: datetime
    ) -> ExternalProductCache | None:
        return await self._session.scalar(
            select(ExternalProductCache).where(
                ExternalProductCache.provider == provider,
                ExternalProductCache.barcode == barcode,
                ExternalProductCache.expires_at > now,
            )
        )

    async def cache(
        self,
        *,
        provider: str,
        barcode: str,
        response_json: dict[str, object],
        http_status: int,
        fetched_at: datetime,
        expires_at: datetime,
        last_modified_at: datetime | None,
    ) -> None:
        statement = insert(ExternalProductCache).values(
            provider=provider,
            barcode=barcode,
            response_json=response_json,
            http_status=http_status,
            fetched_at=fetched_at,
            expires_at=expires_at,
            last_modified_at=last_modified_at,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    ExternalProductCache.provider,
                    ExternalProductCache.barcode,
                ],
                set_={
                    "response_json": statement.excluded.response_json,
                    "http_status": statement.excluded.http_status,
                    "fetched_at": statement.excluded.fetched_at,
                    "expires_at": statement.excluded.expires_at,
                    "last_modified_at": statement.excluded.last_modified_at,
                },
            )
        )

    async def find_ingredient_by_source(
        self, user_id: int, provider: str, external_code: str
    ) -> Ingredient | None:
        return await self._session.scalar(
            select(Ingredient)
            .join(
                IngredientExternalSource,
                IngredientExternalSource.ingredient_id == Ingredient.id,
            )
            .where(
                IngredientExternalSource.user_id == user_id,
                IngredientExternalSource.provider == provider,
                IngredientExternalSource.external_code == external_code,
            )
        )

    async def lock_source(
        self, user_id: int, provider: str, external_code: str
    ) -> None:
        lock_key = f"external-source:{user_id}:{provider}:{external_code}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )

    async def delete_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(ExternalProductCache).where(ExternalProductCache.expires_at <= now)
        )
        return int(result.rowcount or 0)

    async def add_source(
        self,
        *,
        user_id: int,
        ingredient_id: int,
        provider: str,
        external_code: str,
        source_snapshot_json: dict[str, object],
    ) -> None:
        await self._session.execute(
            insert(IngredientExternalSource).values(
                user_id=user_id,
                ingredient_id=ingredient_id,
                provider=provider,
                external_code=external_code,
                source_snapshot_json=source_snapshot_json,
            )
        )
