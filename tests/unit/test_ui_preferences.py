from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.db.models.ui_preference import UserUIPreference
from app.services.ui_preferences import UIPreferenceService
from app.ui_preferences import DefaultSection, ThemeMode, WeightUnit
from app.web.schemas import UIPreferencesUpdateRequest


async def test_service_creates_default_preferences() -> None:
    preference = UserUIPreference(
        user_id=17,
        theme_mode=ThemeMode.SYSTEM,
        default_section=DefaultSection.RATION,
        default_weight_unit=WeightUnit.KG,
        compact_lists=False,
        updated_at=datetime.now(UTC),
    )
    repository = AsyncMock()
    repository.get_or_create.return_value = preference

    result = await UIPreferenceService(repository).get(17)

    assert result is preference
    repository.get_or_create.assert_awaited_once_with(17)


async def test_service_updates_only_requested_preferences() -> None:
    preference = UserUIPreference(
        user_id=17,
        theme_mode=ThemeMode.DARK,
        default_section=DefaultSection.FOOD,
        default_weight_unit=WeightUnit.KG,
        compact_lists=True,
        updated_at=datetime.now(UTC),
    )
    repository = AsyncMock()
    repository.get_or_create.return_value = preference
    repository.update.return_value = preference

    result = await UIPreferenceService(repository).update(
        17,
        theme_mode=ThemeMode.DARK,
        default_section=DefaultSection.FOOD,
        compact_lists=True,
    )

    assert result is preference
    repository.update.assert_awaited_once_with(
        17,
        theme_mode=ThemeMode.DARK,
        default_section=DefaultSection.FOOD,
        default_weight_unit=None,
        compact_lists=True,
    )


def test_empty_update_payload_is_rejected() -> None:
    with pytest.raises(ValueError):
        UIPreferencesUpdateRequest()
