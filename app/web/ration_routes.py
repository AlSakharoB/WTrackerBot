from datetime import date

from fastapi import APIRouter

from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.services.diary import DaySummary, DiaryService
from app.services.nutrition import MacroPercentages, NutritionService, NutritionValues
from app.utils.datetime import local_today
from app.web.dependencies import CurrentUser, DatabaseSession
from app.web.ration_schemas import (
    RationDayResponse,
    RationEntryResponse,
    RationGoalResponse,
    RationMacroPercentagesResponse,
    RationMealResponse,
    RationNutritionResponse,
    RationSummaryResponse,
)

router = APIRouter(prefix="/api/v1/ration")

MEAL_LABELS = {
    MealType.BREAKFAST: "Завтрак",
    MealType.LUNCH: "Обед",
    MealType.DINNER: "Ужин",
    MealType.SNACK: "Перекус",
    MealType.OTHER: "Другое",
}
DEFAULT_MEALS = (
    MealType.BREAKFAST,
    MealType.LUNCH,
    MealType.DINNER,
    MealType.SNACK,
)


def diary_service(session: DatabaseSession) -> DiaryService:
    return DiaryService(
        DiaryRepository(session),
        IngredientRepository(session),
        DishRepository(session),
        NutritionGoalRepository(session),
    )


def nutrition_response(values: NutritionValues) -> RationNutritionResponse:
    return RationNutritionResponse(
        energy_kcal=str(values.kcal),
        protein_g=str(values.protein),
        fat_g=str(values.fat),
        carbs_g=str(values.carbs),
    )


def entry_nutrition(entry: DiaryEntry) -> NutritionValues:
    return NutritionValues(
        kcal=entry.kcal_snapshot,
        protein=entry.protein_snapshot,
        fat=entry.fat_snapshot,
        carbs=entry.carbs_snapshot,
    )


def macro_response(
    percentages: MacroPercentages,
) -> RationMacroPercentagesResponse:
    rounded = NutritionService.round_macro_percentages(percentages)
    return RationMacroPercentagesResponse(
        protein=int(rounded.protein),
        fat=int(rounded.fat),
        carbs=int(rounded.carbs),
    )


def goal_response(summary: DaySummary) -> RationGoalResponse | None:
    goal = summary.nutrition_goal
    if goal is None:
        return None
    return RationGoalResponse(
        energy_kcal=str(goal.kcal_target) if goal.kcal_target is not None else None,
        protein_g=(
            str(goal.protein_target_g) if goal.protein_target_g is not None else None
        ),
        fat_g=str(goal.fat_target_g) if goal.fat_target_g is not None else None,
        carbs_g=str(goal.carbs_target_g) if goal.carbs_target_g is not None else None,
    )


def summary_response(
    summary: DaySummary,
    user: CurrentUser,
) -> RationSummaryResponse:
    today = local_today(user.timezone)
    return RationSummaryResponse(
        date=summary.entry_date,
        timezone=user.timezone,
        number_format=user.number_format,
        is_today=summary.entry_date == today,
        is_future=summary.entry_date > today,
        entry_count=len(summary.entries),
        totals=nutrition_response(summary.totals),
        macro_percentages=macro_response(summary.macro_percentages),
        goal=goal_response(summary),
    )


def entry_response(entry: DiaryEntry) -> RationEntryResponse:
    source_id = (
        entry.ingredient_id
        if entry.entry_type is DiaryEntryType.INGREDIENT
        else entry.dish_id
    )
    return RationEntryResponse(
        id=str(entry.id),
        type=entry.entry_type,
        source_id=str(source_id) if source_id is not None else None,
        source_available=source_id is not None,
        source_name=entry.source_name,
        grams=str(entry.grams),
        meal_type=entry.meal_type,
        nutrition=nutrition_response(entry_nutrition(entry)),
        created_at=entry.created_at,
    )


def meals_response(entries: list[DiaryEntry]) -> list[RationMealResponse]:
    grouped = {meal_type: [] for meal_type in MealType}
    for entry in entries:
        grouped[entry.meal_type].append(entry)
    visible_meals = [*DEFAULT_MEALS]
    if grouped[MealType.OTHER]:
        visible_meals.append(MealType.OTHER)
    result = []
    for meal_type in visible_meals:
        meal_entries = grouped[meal_type]
        totals = NutritionService.sum_nutrition(
            entry_nutrition(entry) for entry in meal_entries
        )
        result.append(
            RationMealResponse(
                type=meal_type,
                label=MEAL_LABELS[meal_type],
                totals=nutrition_response(totals),
                entries=[entry_response(entry) for entry in meal_entries],
            )
        )
    return result


async def get_summary(
    entry_date: date,
    user: CurrentUser,
    session: DatabaseSession,
) -> DaySummary:
    return await diary_service(session).get_day(user.id, entry_date)


@router.get("/{entry_date}", response_model=RationDayResponse)
async def get_ration_day(
    entry_date: date,
    user: CurrentUser,
    session: DatabaseSession,
) -> RationDayResponse:
    summary = await get_summary(entry_date, user, session)
    base = summary_response(summary, user)
    return RationDayResponse(
        **base.model_dump(),
        meals=meals_response(summary.entries),
    )


@router.get("/{entry_date}/summary", response_model=RationSummaryResponse)
async def get_ration_summary(
    entry_date: date,
    user: CurrentUser,
    session: DatabaseSession,
) -> RationSummaryResponse:
    summary = await get_summary(entry_date, user, session)
    return summary_response(summary, user)
