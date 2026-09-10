from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class WeightEntryResponse(BaseModel):
    id: str
    weight_kg: str
    measured_at: datetime
    note: str | None
    updated_at: datetime


class WeightChartPointResponse(WeightEntryResponse):
    moving_average_7d_kg: str | None


class WeightGoalProgressResponse(BaseModel):
    percentage: str
    completed_kg: str
    remaining_kg: str
    achieved: bool


class WeightGoalResponse(BaseModel):
    id: str
    target_weight_kg: str
    start_weight_kg: str | None
    target_date: date | None
    current_weight_kg: str | None
    progress: WeightGoalProgressResponse | None
    updated_at: datetime


class WeightRangeResponse(BaseModel):
    timezone: str
    date_from: date
    date_to: date
    current: WeightEntryResponse | None
    previous: WeightEntryResponse | None
    change_from_previous_kg: str | None
    period_change_kg: str | None
    minimum_kg: str | None
    maximum_kg: str | None
    goal: WeightGoalResponse | None
    points: list[WeightChartPointResponse]
    history: list[WeightEntryResponse]


class WeightEntryCreateRequest(BaseModel):
    weight_kg: str = Field(min_length=1, max_length=32)
    measured_at: datetime
    note: str | None = Field(default=None, max_length=1000)


class WeightEntryUpdateRequest(BaseModel):
    expected_updated_at: datetime
    weight_kg: str | None = Field(default=None, min_length=1, max_length=32)
    measured_at: datetime | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> "WeightEntryUpdateRequest":
        if not ({"weight_kg", "measured_at", "note"} & self.model_fields_set):
            raise ValueError("At least one editable field must be provided")
        return self


class WeightGoalUpdateRequest(BaseModel):
    enabled: bool = True
    target_weight_kg: str | None = Field(default=None, min_length=1, max_length=32)
    target_date: date | None = None

    @model_validator(mode="after")
    def require_target(self) -> "WeightGoalUpdateRequest":
        if self.enabled and self.target_weight_kg is None:
            raise ValueError("Target weight is required for an enabled goal")
        return self
