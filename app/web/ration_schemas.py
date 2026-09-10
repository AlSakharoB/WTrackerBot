from datetime import date, datetime

from pydantic import BaseModel

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
