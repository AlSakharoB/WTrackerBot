from dataclasses import dataclass

from app.db.models.user import User
from app.exceptions import NotFoundError
from app.repositories.privacy import PrivacyRepository


@dataclass(frozen=True, slots=True)
class UserDataSummary:
    ingredients: int
    dishes: int
    diary_entries: int
    weight_entries: int
    active_goals: int


class PrivacyService:
    def __init__(
        self,
        repository: PrivacyRepository,
        *,
        default_timezone: str,
    ) -> None:
        self._repository = repository
        self._default_timezone = default_timezone

    async def summary(self, user_id: int) -> UserDataSummary:
        return UserDataSummary(*await self._repository.counts(user_id))

    async def clear_user_data(self, user_id: int) -> User:
        async with self._repository.atomic():
            await self._repository.delete_diary_entries(user_id)
            await self._repository.delete_dish_ingredients(user_id)
            await self._repository.delete_dishes(user_id)
            await self._repository.delete_ingredients(user_id)
            await self._repository.delete_weight_entries(user_id)
            await self._repository.delete_weight_goals(user_id)
            await self._repository.delete_nutrition_goals(user_id)
            await self._repository.delete_reminder_settings(user_id)
            user = await self._repository.reset_preferences(
                user_id,
                default_timezone=self._default_timezone,
            )
            if user is None:
                raise NotFoundError("Пользователь не найден.")
        return user
