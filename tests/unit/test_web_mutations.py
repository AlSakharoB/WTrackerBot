from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from app.db.models.web_mutation import WebMutationReceipt
from app.exceptions import IdempotencyConflictError
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.services.web_mutations import WebMutationService, fingerprint_web_request


def test_request_fingerprint_is_canonical() -> None:
    first = fingerprint_web_request({"weight_g": "100", "meal": "lunch"})
    second = fingerprint_web_request({"meal": "lunch", "weight_g": "100"})

    assert first == second
    assert len(first) == 64
    assert first != fingerprint_web_request({"meal": "lunch", "weight_g": "101"})


async def test_repository_deletes_expired_receipts() -> None:
    result = Mock(rowcount=3)
    session = Mock()
    session.execute = AsyncMock(return_value=result)
    repository = WebMutationReceiptRepository(session)

    deleted = await repository.delete_expired(datetime.now(UTC))

    assert deleted == 3
    session.execute.assert_awaited_once()


def make_receipt(
    *,
    payload: object,
    expires_at: datetime,
) -> WebMutationReceipt:
    return WebMutationReceipt(
        id=1,
        user_id=7,
        operation="ration.create",
        idempotency_key="request-1",
        request_fingerprint=fingerprint_web_request(payload),
        response_status=201,
        response_body_json={"id": "42"},
        expires_at=expires_at,
    )


async def test_mutation_service_replays_same_request() -> None:
    now = datetime.now(UTC)
    repository = Mock()
    repository.lock_key = AsyncMock()
    repository.get_by_key = AsyncMock(
        return_value=make_receipt(
            payload={"grams": "100"}, expires_at=now + timedelta(hours=1)
        )
    )
    service = WebMutationService(repository, receipt_ttl_hours=24)
    command = AsyncMock()

    result = await service.execute(
        user_id=7,
        operation="ration.create",
        idempotency_key="request-1",
        payload={"grams": "100"},
        command=command,
        now=now,
    )

    assert result.replayed is True
    assert result.status_code == 201
    assert result.body == {"id": "42"}
    command.assert_not_awaited()


async def test_mutation_service_rejects_key_reuse_with_other_payload() -> None:
    now = datetime.now(UTC)
    repository = Mock()
    repository.lock_key = AsyncMock()
    repository.get_by_key = AsyncMock(
        return_value=make_receipt(
            payload={"grams": "100"}, expires_at=now + timedelta(hours=1)
        )
    )
    service = WebMutationService(repository, receipt_ttl_hours=24)

    with pytest.raises(IdempotencyConflictError):
        await service.execute(
            user_id=7,
            operation="ration.create",
            idempotency_key="request-1",
            payload={"grams": "200"},
            command=AsyncMock(),
            now=now,
        )


async def test_mutation_service_stores_first_result() -> None:
    now = datetime.now(UTC)
    repository = Mock()
    repository.lock_key = AsyncMock()
    repository.get_by_key = AsyncMock(return_value=None)
    repository.add = AsyncMock()
    service = WebMutationService(repository, receipt_ttl_hours=24)
    command = AsyncMock(return_value=(201, {"id": "42"}))

    result = await service.execute(
        user_id=7,
        operation="ration.create",
        idempotency_key="request-1",
        payload={"grams": "100"},
        command=command,
        now=now,
    )

    assert result.replayed is False
    repository.add.assert_awaited_once_with(
        user_id=7,
        operation="ration.create",
        idempotency_key="request-1",
        request_fingerprint=fingerprint_web_request({"grams": "100"}),
        response_status=201,
        response_body_json={"id": "42"},
        expires_at=now + timedelta(hours=24),
    )
