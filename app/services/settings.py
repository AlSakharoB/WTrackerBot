from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.db.models.user import User
from app.exceptions import NotFoundError, ValidationError
from app.repositories.users import UserRepository
from app.user_settings import AfterFoodAddAction, NumberFormat

POPULAR_TIMEZONES = (
    "Europe/Moscow",
    "Europe/Berlin",
    "Europe/London",
    "Asia/Dubai",
    "Asia/Almaty",
    "Asia/Tbilisi",
)


class UserSettingsService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def set_timezone(self, user_id: int, timezone: str) -> User:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as error:
            raise ValidationError("Неизвестный часовой пояс.") from error
        user = await self._repository.update_settings(user_id, timezone=timezone)
        return self._require_user(user)

    async def set_number_format(
        self,
        user_id: int,
        number_format: NumberFormat,
    ) -> User:
        user = await self._repository.update_settings(
            user_id,
            number_format=number_format,
        )
        return self._require_user(user)

    async def set_after_food_add_action(
        self,
        user_id: int,
        action: AfterFoodAddAction,
    ) -> User:
        user = await self._repository.update_settings(
            user_id,
            after_food_add_action=action,
        )
        return self._require_user(user)

    @staticmethod
    def _require_user(user: User | None) -> User:
        if user is None:
            raise NotFoundError("Пользователь не найден.")
        return user
