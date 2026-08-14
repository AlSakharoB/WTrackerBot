import logging
from dataclasses import dataclass

from app.db.models.user import User
from app.repositories.users import UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelegramUserData:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None


@dataclass(frozen=True, slots=True)
class UserSyncResult:
    user: User
    created: bool


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        *,
        default_timezone: str,
    ) -> None:
        self._repository = repository
        self._default_timezone = default_timezone

    async def sync_telegram_user(self, data: TelegramUserData) -> UserSyncResult:
        user = await self._repository.get_by_telegram_id(data.telegram_id)
        if user is None:
            user, created = await self._repository.create_or_get(
                telegram_id=data.telegram_id,
                username=data.username,
                first_name=data.first_name,
                last_name=data.last_name,
                language_code=data.language_code,
                timezone=self._default_timezone,
            )
            if created:
                logger.info(
                    "New user registered",
                    extra={"operation": "user.register"},
                )
            return UserSyncResult(user=user, created=created)

        telegram_fields = (
            user.username,
            user.first_name,
            user.last_name,
            user.language_code,
        )
        incoming_fields = (
            data.username,
            data.first_name,
            data.last_name,
            data.language_code,
        )
        if telegram_fields != incoming_fields:
            self._repository.update_telegram_data(
                user,
                username=data.username,
                first_name=data.first_name,
                last_name=data.last_name,
                language_code=data.language_code,
            )

        return UserSyncResult(user=user, created=False)
