import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.exceptions import ValidationError
from app.repositories.account_deletion import AccountDeletionRepository
from app.services.privacy import PrivacyService

DELETION_CONFIRMATION_PHRASE = "УДАЛИТЬ"


@dataclass(frozen=True, slots=True)
class AccountDeletionChallenge:
    token: str
    expires_at: datetime


class AccountDeletionService:
    def __init__(
        self,
        repository: AccountDeletionRepository,
        privacy_service: PrivacyService,
        *,
        ttl_minutes: int = 10,
    ) -> None:
        self._repository = repository
        self._privacy_service = privacy_service
        self._ttl = timedelta(minutes=ttl_minutes)

    async def request(
        self,
        user_id: int,
        *,
        now: datetime | None = None,
    ) -> AccountDeletionChallenge:
        current = now or datetime.now(UTC)
        token = secrets.token_urlsafe(32)
        expires_at = current + self._ttl
        await self._repository.replace(
            user_id=user_id,
            token_hash=self._hash(token),
            expires_at=expires_at,
        )
        return AccountDeletionChallenge(token=token, expires_at=expires_at)

    async def confirm(
        self,
        user_id: int,
        *,
        token: str,
        phrase: str,
        now: datetime | None = None,
    ) -> None:
        if phrase != DELETION_CONFIRMATION_PHRASE:
            raise ValidationError("Введите слово УДАЛИТЬ без пробелов.")
        if not token or len(token) > 128:
            raise ValidationError("Запрос на удаление недействителен.")
        current = now or datetime.now(UTC)
        request = await self._repository.get_active_for_update(
            user_id=user_id,
            token_hash=self._hash(token),
            now=current,
        )
        if request is None:
            raise ValidationError("Запрос на удаление истёк. Начните заново.")
        await self._privacy_service.clear_user_data(user_id)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
