from datetime import datetime

from pydantic import BaseModel, model_validator

from app.ui_preferences import DefaultSection, ThemeMode, WeightUnit


class CurrentUserResponse(BaseModel):
    id: str
    telegram_id: str
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    timezone: str
    app_version: str


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(HealthResponse):
    database_revision: str


class UIPreferencesResponse(BaseModel):
    theme_mode: ThemeMode
    default_section: DefaultSection
    default_weight_unit: WeightUnit
    compact_lists: bool
    updated_at: datetime


class UIPreferencesUpdateRequest(BaseModel):
    theme_mode: ThemeMode | None = None
    default_section: DefaultSection | None = None
    default_weight_unit: WeightUnit | None = None
    compact_lists: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UIPreferencesUpdateRequest":
        if not self.model_fields_set or all(
            value is None
            for value in (
                self.theme_mode,
                self.default_section,
                self.default_weight_unit,
                self.compact_lists,
            )
        ):
            raise ValueError("At least one preference must be provided")
        return self
