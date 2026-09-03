from app.db.models.ui_preference import UserUIPreference
from app.repositories.ui_preferences import UIPreferenceRepository
from app.ui_preferences import DefaultSection, ThemeMode, WeightUnit


class UIPreferenceService:
    def __init__(self, repository: UIPreferenceRepository) -> None:
        self._repository = repository

    async def get(self, user_id: int) -> UserUIPreference:
        return await self._repository.get_or_create(user_id)

    async def update(
        self,
        user_id: int,
        *,
        theme_mode: ThemeMode | None = None,
        default_section: DefaultSection | None = None,
        default_weight_unit: WeightUnit | None = None,
        compact_lists: bool | None = None,
    ) -> UserUIPreference:
        await self._repository.get_or_create(user_id)
        preference = await self._repository.update(
            user_id,
            theme_mode=theme_mode,
            default_section=default_section,
            default_weight_unit=default_weight_unit,
            compact_lists=compact_lists,
        )
        if preference is None:
            msg = "UI preferences disappeared during update"
            raise RuntimeError(msg)
        return preference
