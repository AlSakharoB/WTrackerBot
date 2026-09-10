import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.exceptions import IdempotencyConflictError, ValidationError
from app.repositories.account_deletion import AccountDeletionRepository
from app.repositories.external_products import ExternalProductRepository
from app.repositories.web_mutations import WebMutationReceiptRepository

logger = logging.getLogger(__name__)

MutationCommand = Callable[[], Awaitable[tuple[int, dict[str, object]]]]


@dataclass(frozen=True, slots=True)
class WebMutationResult:
    status_code: int
    body: dict[str, object]
    replayed: bool


def fingerprint_web_request(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


class WebMutationService:
    def __init__(
        self,
        repository: WebMutationReceiptRepository,
        *,
        receipt_ttl_hours: int,
    ) -> None:
        self._repository = repository
        self._receipt_ttl = timedelta(hours=receipt_ttl_hours)

    async def execute(
        self,
        *,
        user_id: int,
        operation: str,
        idempotency_key: str,
        payload: object,
        command: MutationCommand,
        now: datetime | None = None,
    ) -> WebMutationResult:
        self._validate_key(operation, idempotency_key)
        current = now or datetime.now(UTC)
        fingerprint = fingerprint_web_request(payload)
        await self._repository.lock_key(
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
        )
        receipt = await self._repository.get_by_key(
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
        )
        if receipt is not None and receipt.expires_at <= current:
            await self._repository.remove(receipt)
            receipt = None
        if receipt is not None:
            if receipt.request_fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "Idempotency key was reused with a different payload"
                )
            return WebMutationResult(
                status_code=receipt.response_status,
                body=receipt.response_body_json,
                replayed=True,
            )

        status_code, body = await command()
        await self._repository.add(
            user_id=user_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            response_status=status_code,
            response_body_json=body,
            expires_at=current + self._receipt_ttl,
        )
        return WebMutationResult(
            status_code=status_code,
            body=body,
            replayed=False,
        )

    @staticmethod
    def _validate_key(operation: str, idempotency_key: str) -> None:
        if not operation or len(operation) > 64:
            raise ValidationError("Invalid idempotent operation name")
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValidationError("Invalid Idempotency-Key")


async def run_web_mutation_receipt_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: int,
) -> None:
    while True:
        try:
            async with session_factory() as session, session.begin():
                now = datetime.now(UTC)
                deleted = await WebMutationReceiptRepository(session).delete_expired(
                    now
                )
                deleted += await AccountDeletionRepository(session).delete_expired(now)
                deleted += await ExternalProductRepository(session).delete_expired(now)
            if deleted:
                logger.info(
                    "Expired Web API maintenance records removed count=%d",
                    deleted,
                    extra={"operation": "web.idempotency.cleanup"},
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Web API mutation receipt cleanup failed",
                extra={"operation": "web.idempotency.cleanup"},
            )
        await asyncio.sleep(interval_seconds)
