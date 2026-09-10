from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.db.models.diary import DiaryEntryType, MealType
from app.user_settings import NumberFormat


class RationNutritionResponse(BaseModel):
    energy_kcal: str
    protein_g: str
    fat_g: str
    carbs_g: str


class RationMacroPercentagesResponse(BaseModel):
    protein: int
    fat: int
    carbs: int


class RationGoalResponse(BaseModel):
    energy_kcal: str | None
    protein_g: str | None
    fat_g: str | None
    carbs_g: str | None


class RationEntryResponse(BaseModel):
    id: str
    type: DiaryEntryType
    source_id: str | None
    source_available: bool
    source_name: str
    grams: str
    meal_type: MealType
    nutrition: RationNutritionResponse
    created_at: datetime
    updated_at: datetime


class RationSourceResponse(BaseModel):
    id: str
    type: DiaryEntryType
    name: str
    default_grams: str
    nutrition_per_100g: RationNutritionResponse
    usage_count: int
    last_used_at: datetime | None


class RationSourceListResponse(BaseModel):
    items: list[RationSourceResponse]


class RationEntryCreateRequest(BaseModel):
    source_type: DiaryEntryType
    source_id: str = Field(pattern=r"^[1-9]\d*$", max_length=20)
    grams: str = Field(min_length=1, max_length=32)
    meal_type: MealType


class RationEntryUpdateRequest(BaseModel):
    expected_updated_at: datetime
    grams: str | None = Field(default=None, min_length=1, max_length=32)
    meal_type: MealType | None = None
    entry_date: date | None = None

    @model_validator(mode="after")
    def require_change(self) -> "RationEntryUpdateRequest":
        if all(
            value is None for value in (self.grams, self.meal_type, self.entry_date)
        ):
            raise ValueError("At least one editable field must be provided")
        return self


class RationEntryCopyRequest(BaseModel):
    entry_date: date
    meal_type: MealType | None = None


RationSourceKind = Literal["all", "ingredient", "dish"]


class RationMealResponse(BaseModel):
    type: MealType
    label: str
    totals: RationNutritionResponse
    entries: list[RationEntryResponse]


class RationSummaryResponse(BaseModel):
    date: date
    timezone: str
    number_format: NumberFormat
    is_today: bool
    is_future: bool
    entry_count: int
    totals: RationNutritionResponse
    macro_percentages: RationMacroPercentagesResponse
    goal: RationGoalResponse | None


class RationDayResponse(RationSummaryResponse):
    meals: list[RationMealResponse]
