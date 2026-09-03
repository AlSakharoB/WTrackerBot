from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.web_mutation import WebMutationReceipt


class WebMutationReceiptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_key(
        self,
        *,
        user_id: int,
        operation: str,
        idempotency_key: str,
    ) -> None:
        scope = f"{user_id}:{operation}:{idempotency_key}"
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": scope},
        )

    async def get_by_key(
        self,
        *,
        user_id: int,
        operation: str,
        idempotency_key: str,
    ) -> WebMutationReceipt | None:
        statement = select(WebMutationReceipt).where(
            WebMutationReceipt.user_id == user_id,
            WebMutationReceipt.operation == operation,
            WebMutationReceipt.idempotency_key == idempotency_key,
        )
        return await self._session.scalar(statement)

    async def remove(self, receipt: WebMutationReceipt) -> None:
        await self._session.delete(receipt)
        await self._session.flush()

    async def add(
        self,
        *,
        user_id: int,
        operation: str,
        idempotency_key: str,
        request_fingerprint: str,
        response_status: int,
        response_body_json: dict[str, object],
        expires_at: datetime,
    ) -> WebMutationReceipt:
        receipt = WebMutationReceipt(
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            response_status=response_status,
            response_body_json=response_body_json,
            expires_at=expires_at,
        )
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def delete_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(WebMutationReceipt).where(WebMutationReceipt.expires_at <= now)
        )
        return result.rowcount or 0  # type: ignore[attr-defined]
