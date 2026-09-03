from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models.reminder import ReminderType
from app.user_settings import AfterFoodAddAction, NumberFormat


class ProfileResponse(BaseModel):
    id: str
    telegram_id: str
    username: str | None
    first_name: str | None
    last_name: str | None
    photo_url: str | None
    language_code: str | None
    timezone: str
    number_format: NumberFormat
    after_food_add_action: AfterFoodAddAction
    confirm_deletions: bool
    app_version: str
    reminders_enabled: bool


class ProfileSettingsUpdateRequest(BaseModel):
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    number_format: NumberFormat | None = None
    after_food_add_action: AfterFoodAddAction | None = None
    confirm_deletions: bool | None = None

    @model_validator(mode="after")
    def require_value(self) -> "ProfileSettingsUpdateRequest":
        if not self.model_fields_set or all(
            value is None
            for value in (
                self.timezone,
                self.number_format,
                self.after_food_add_action,
                self.confirm_deletions,
            )
        ):
            raise ValueError("At least one setting must be provided")
        return self


class ProfileStatsResponse(BaseModel):
    diary_days: int
    ingredients: int
    dishes: int
    diary_entries: int
    weight_entries: int
    active_weight_goals: int
    share_packages: int
    imported_packages: int


class NutritionGoalResponse(BaseModel):
    id: str
    energy_kcal: str | None
    protein_g: str | None
    fat_g: str | None
    carbs_g: str | None
    effective_from: date
    effective_to: date | None


class NutritionGoalUpdateRequest(BaseModel):
    enabled: bool = True
    energy_kcal: str | None = Field(default=None, max_length=32)
    protein_g: str | None = Field(default=None, max_length=32)
    fat_g: str | None = Field(default=None, max_length=32)
    carbs_g: str | None = Field(default=None, max_length=32)
    effective_from: date | None = None


def _validate_weekdays(value: list[int] | None) -> list[int] | None:
    if value is None:
        return None
    if not value or len(value) > 7 or len(set(value)) != len(value):
        raise ValueError("Select at least one unique weekday")
    if any(day < 0 or day > 6 for day in value):
        raise ValueError("Weekday must be between 0 and 6")
    return value


class ReminderResponse(BaseModel):
    id: str
    type: ReminderType
    enabled: bool
    time_local: str
    weekdays: list[int]
    updated_at: datetime


class ReminderCreateRequest(BaseModel):
    type: ReminderType
    time_local: str = Field(min_length=4, max_length=5)
    weekdays: list[int]

    _weekdays = field_validator("weekdays")(_validate_weekdays)


class ReminderUpdateRequest(BaseModel):
    enabled: bool | None = None
    time_local: str | None = Field(default=None, min_length=4, max_length=5)
    weekdays: list[int] | None = None

    _weekdays = field_validator("weekdays")(_validate_weekdays)

    @model_validator(mode="after")
    def require_value(self) -> "ReminderUpdateRequest":
        if not self.model_fields_set or all(
            value is None for value in (self.enabled, self.time_local, self.weekdays)
        ):
            raise ValueError("At least one reminder setting must be provided")
        return self


class DeletionRequestResponse(BaseModel):
    confirmation_token: str
    confirmation_phrase: str
    expires_at: datetime


class DeletionConfirmRequest(BaseModel):
    confirmation_token: str = Field(min_length=1, max_length=128)
    confirmation_phrase: str = Field(min_length=1, max_length=32)


class OperationResponse(BaseModel):
    status: str
