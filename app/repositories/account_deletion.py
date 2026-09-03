from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account_deletion import AccountDeletionRequest


class AccountDeletionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace(
        self,
        *,
        user_id: int,
        token_hash: str,
        expires_at: datetime,
    ) -> AccountDeletionRequest:
        statement = (
            insert(AccountDeletionRequest)
            .values(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=[AccountDeletionRequest.user_id],
                set_={"token_hash": token_hash, "expires_at": expires_at},
            )
            .returning(AccountDeletionRequest)
            .execution_options(populate_existing=True)
        )
        return (await self._session.scalars(statement)).one()

    async def get_active_for_update(
        self,
        *,
        user_id: int,
        token_hash: str,
        now: datetime,
    ) -> AccountDeletionRequest | None:
        statement = (
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.user_id == user_id,
                AccountDeletionRequest.token_hash == token_hash,
                AccountDeletionRequest.expires_at > now,
            )
            .with_for_update()
        )
        return await self._session.scalar(statement)

    async def delete_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(AccountDeletionRequest).where(
                AccountDeletionRequest.expires_at <= now
            )
        )
        return result.rowcount or 0  # type: ignore[attr-defined]
