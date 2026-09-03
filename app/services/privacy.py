from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.db.models.user import User
from app.exceptions import NotFoundError
from app.repositories.privacy import PrivacyExportRecords, PrivacyRepository


@dataclass(frozen=True, slots=True)
class UserDataSummary:
    ingredients: int
    dishes: int
    diary_entries: int
    weight_entries: int
    active_goals: int
    share_packages: int = 0
    imported_packages: int = 0


@dataclass(frozen=True, slots=True)
class UserProfileStats:
    diary_days: int
    ingredients: int
    dishes: int
    weight_entries: int


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

    async def profile_stats(self, user_id: int) -> UserProfileStats:
        return UserProfileStats(*await self._repository.profile_stats(user_id))

    async def export(self, user_id: int) -> dict[str, object]:
        records = await self._repository.export_records(user_id)
        if records is None:
            raise NotFoundError("Пользователь не найден.")
        return self._serialize_export(records)

    async def clear_user_data(self, user_id: int) -> User:
        async with self._repository.atomic():
            await self._repository.delete_share_imports(user_id)
            await self._repository.delete_share_packages(user_id)
            await self._repository.delete_diary_entries(user_id)
            await self._repository.delete_dish_ingredients(user_id)
            await self._repository.delete_dishes(user_id)
            await self._repository.delete_ingredients(user_id)
            await self._repository.delete_weight_entries(user_id)
            await self._repository.delete_weight_goals(user_id)
            await self._repository.delete_nutrition_goals(user_id)
            await self._repository.delete_reminder_settings(user_id)
            await self._repository.delete_web_state(user_id)
            user = await self._repository.reset_preferences(
                user_id,
                default_timezone=self._default_timezone,
            )
            if user is None:
                raise NotFoundError("Пользователь не найден.")
        return user

    @staticmethod
    def _serialize_export(records: PrivacyExportRecords) -> dict[str, object]:
        def decimal(value: object) -> str | None:
            return None if value is None else str(value)

        def timestamp(value: date | datetime | None) -> str | None:
            return None if value is None else value.isoformat()

        def enum_value(value: object) -> str:
            return str(getattr(value, "value", value))

        return {
            "exported_at": timestamp(datetime.now(UTC)),
            "profile": {
                "telegram_id": str(records.user.telegram_id),
                "username": records.user.username,
                "first_name": records.user.first_name,
                "last_name": records.user.last_name,
                "language_code": records.user.language_code,
                "timezone": records.user.timezone,
                "number_format": enum_value(records.user.number_format),
                "after_food_add_action": enum_value(records.user.after_food_add_action),
                "confirm_deletions": records.user.confirm_deletions,
            },
            "interface_preferences": (
                {
                    "theme_mode": enum_value(records.ui_preferences.theme_mode),
                    "default_section": enum_value(
                        records.ui_preferences.default_section
                    ),
                    "compact_lists": records.ui_preferences.compact_lists,
                }
                if records.ui_preferences is not None
                else None
            ),
            "ingredients": [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "energy_kcal_per_100g": decimal(item.kcal_per_100g),
                    "protein_g_per_100g": decimal(item.protein_per_100g),
                    "fat_g_per_100g": decimal(item.fat_per_100g),
                    "carbs_g_per_100g": decimal(item.carbs_per_100g),
                }
                for item in records.ingredients
            ],
            "dishes": [
                {
                    "id": str(item.id),
                    "name": item.name,
                    "ingredients": [
                        {
                            "ingredient_id": str(component.ingredient_id),
                            "weight_g": decimal(component.grams),
                        }
                        for component in records.dish_ingredients
                        if component.dish_id == item.id
                    ],
                }
                for item in records.dishes
            ],
            "ration": [
                {
                    "id": str(item.id),
                    "date": item.entry_date.isoformat(),
                    "type": enum_value(item.entry_type),
                    "source_name": item.source_name,
                    "weight_g": decimal(item.grams),
                    "meal": enum_value(item.meal_type),
                    "energy_kcal": decimal(item.kcal_snapshot),
                    "protein_g": decimal(item.protein_snapshot),
                    "fat_g": decimal(item.fat_snapshot),
                    "carbs_g": decimal(item.carbs_snapshot),
                }
                for item in records.diary_entries
            ],
            "weight_entries": [
                {
                    "id": str(item.id),
                    "weight_kg": decimal(item.weight_kg),
                    "measured_at": timestamp(item.measured_at),
                    "note": item.note,
                }
                for item in records.weight_entries
            ],
            "weight_goals": [
                {
                    "id": str(item.id),
                    "target_weight_kg": decimal(item.target_weight_kg),
                    "start_weight_kg": decimal(item.start_weight_kg),
                    "target_date": timestamp(item.target_date),
                    "status": enum_value(item.status),
                }
                for item in records.weight_goals
            ],
            "nutrition_goals": [
                {
                    "id": str(item.id),
                    "energy_kcal": decimal(item.kcal_target),
                    "protein_g": decimal(item.protein_target_g),
                    "fat_g": decimal(item.fat_target_g),
                    "carbs_g": decimal(item.carbs_target_g),
                    "effective_from": item.effective_from.isoformat(),
                    "effective_to": timestamp(item.effective_to),
                }
                for item in records.nutrition_goals
            ],
            "reminders": [
                {
                    "id": str(item.id),
                    "type": enum_value(item.reminder_type),
                    "enabled": item.enabled,
                    "time_local": item.time_local.strftime("%H:%M"),
                    "weekdays_mask": item.weekdays_mask,
                }
                for item in records.reminders
            ],
            "sharing": {
                "created_packages": len(records.share_packages),
                "imported_packages": len(records.share_imports),
            },
        }
