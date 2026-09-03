from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.exceptions import ValidationError
from app.services.account_deletion import (
    DELETION_CONFIRMATION_PHRASE,
    AccountDeletionService,
)


async def test_account_deletion_requires_exact_phrase_and_active_token() -> None:
    repository = AsyncMock()
    privacy = AsyncMock()
    now = datetime(2026, 9, 3, 12, tzinfo=UTC)
    service = AccountDeletionService(repository, privacy)

    challenge = await service.request(7, now=now)

    assert challenge.expires_at == now + timedelta(minutes=10)
    assert len(challenge.token) >= 32
    stored_hash = repository.replace.await_args.kwargs["token_hash"]
    assert stored_hash != challenge.token

    with pytest.raises(ValidationError, match="УДАЛИТЬ"):
        await service.confirm(
            7,
            token=challenge.token,
            phrase="удалить",
            now=now,
        )
    repository.get_active_for_update.assert_not_awaited()

    repository.get_active_for_update.return_value = SimpleNamespace(id=1)
    await service.confirm(
        7,
        token=challenge.token,
        phrase=DELETION_CONFIRMATION_PHRASE,
        now=now,
    )

    repository.get_active_for_update.assert_awaited_once_with(
        user_id=7,
        token_hash=stored_hash,
        now=now,
    )
    privacy.clear_user_data.assert_awaited_once_with(7)


async def test_account_deletion_rejects_expired_or_reused_request() -> None:
    repository = AsyncMock()
    repository.get_active_for_update.return_value = None
    privacy = AsyncMock()
    service = AccountDeletionService(repository, privacy)

    with pytest.raises(ValidationError, match="истёк"):
        await service.confirm(
            11,
            token="expired-token",
            phrase=DELETION_CONFIRMATION_PHRASE,
        )

    privacy.clear_user_data.assert_not_awaited()
