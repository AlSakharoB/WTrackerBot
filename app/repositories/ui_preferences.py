from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ui_preference import UserUIPreference
from app.ui_preferences import DefaultSection, ThemeMode, WeightUnit


class UIPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> UserUIPreference | None:
        statement = (
            select(UserUIPreference)
            .where(UserUIPreference.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)

    async def get_or_create(self, user_id: int) -> UserUIPreference:
        statement = (
            insert(UserUIPreference)
            .values(user_id=user_id)
            .on_conflict_do_nothing(index_elements=[UserUIPreference.user_id])
            .returning(UserUIPreference)
        )
        preference = await self._session.scalar(statement)
        if preference is not None:
            return preference

        preference = await self.get(user_id)
        if preference is None:
            msg = "UI preference conflict occurred but the row was not found"
            raise RuntimeError(msg)
        return preference

    async def update(
        self,
        user_id: int,
        *,
        theme_mode: ThemeMode | None = None,
        default_section: DefaultSection | None = None,
        default_weight_unit: WeightUnit | None = None,
        compact_lists: bool | None = None,
    ) -> UserUIPreference | None:
        values: dict[str, str | bool | object] = {}
        if theme_mode is not None:
            values["theme_mode"] = theme_mode.value
        if default_section is not None:
            values["default_section"] = default_section.value
        if default_weight_unit is not None:
            values["default_weight_unit"] = default_weight_unit.value
        if compact_lists is not None:
            values["compact_lists"] = compact_lists

        if not values:
            return await self.get(user_id)

        values["updated_at"] = func.now()
        statement = (
            update(UserUIPreference)
            .where(UserUIPreference.user_id == user_id)
            .values(**values)
            .returning(UserUIPreference)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)
