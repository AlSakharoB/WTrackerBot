from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.ingredient import Ingredient
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRecord, DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.search import normalize_search_text
from app.services.diary import DaySummary, DiaryService, parse_entry_grams
from app.services.nutrition import (
    MacroPercentages,
    NutritionComponent,
    NutritionService,
    NutritionValues,
)
from app.services.web_mutations import WebMutationService
from app.utils.datetime import local_today
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.ration_schemas import (
    RationDayResponse,
    RationEntryCopyRequest,
    RationEntryCreateRequest,
    RationEntryResponse,
    RationEntryUpdateRequest,
    RationGoalResponse,
    RationMacroPercentagesResponse,
    RationMealResponse,
    RationNutritionResponse,
    RationSourceKind,
    RationSourceListResponse,
    RationSourceResponse,
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
        updated_at=entry.updated_at,
    )


def mutation_service(request: Request, session: DatabaseSession) -> WebMutationService:
    return WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    )


def ingredient_nutrition(ingredient: Ingredient) -> NutritionValues:
    return NutritionValues(
        kcal=ingredient.kcal_per_100g,
        protein=ingredient.protein_per_100g,
        fat=ingredient.fat_per_100g,
        carbs=ingredient.carbs_per_100g,
    )


def dish_nutrition(record: DishRecord) -> tuple[Decimal, NutritionValues]:
    calculated = NutritionService.calculate_dish_nutrition(
        NutritionComponent(
            nutrition_per_100g=ingredient_nutrition(item.ingredient),
            grams=item.grams,
        )
        for item in record.components
    )
    return calculated.total_weight, calculated.per_100g


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


@router.get("/sources", response_model=RationSourceListResponse)
async def list_ration_sources(
    user: CurrentUser,
    session: DatabaseSession,
    q: str | None = Query(default=None, max_length=100),
    kind: RationSourceKind = "all",
    limit: int = Query(default=30, ge=1, le=100),
) -> RationSourceListResponse:
    query = normalize_search_text(q or "") or None
    fetch_limit = 100 if kind == "all" else limit
    usage = await DiaryRepository(session).source_usage(user.id)
    items: list[RationSourceResponse] = []

    if kind in {"all", "ingredient"}:
        ingredients = await IngredientRepository(session).search(
            user.id,
            query=query,
            limit=fetch_limit,
        )
        for ingredient in ingredients:
            source_usage = usage.get((DiaryEntryType.INGREDIENT, ingredient.id))
            items.append(
                RationSourceResponse(
                    id=str(ingredient.id),
                    type=DiaryEntryType.INGREDIENT,
                    name=ingredient.name,
                    default_grams="100",
                    nutrition_per_100g=nutrition_response(
                        ingredient_nutrition(ingredient)
                    ),
                    usage_count=source_usage.count if source_usage else 0,
                    last_used_at=(source_usage.last_used_at if source_usage else None),
                )
            )

    if kind in {"all", "dish"}:
        records = await DishRepository(session).search_records(
            user.id,
            query=query,
            limit=fetch_limit,
        )
        for record in records:
            source_usage = usage.get((DiaryEntryType.DISH, record.dish.id))
            default_grams, per_100g = dish_nutrition(record)
            items.append(
                RationSourceResponse(
                    id=str(record.dish.id),
                    type=DiaryEntryType.DISH,
                    name=record.dish.name,
                    default_grams=str(default_grams),
                    nutrition_per_100g=nutrition_response(per_100g),
                    usage_count=source_usage.count if source_usage else 0,
                    last_used_at=(source_usage.last_used_at if source_usage else None),
                )
            )

    if query is None:
        items.sort(
            key=lambda item: (
                -item.usage_count,
                -(item.last_used_at.timestamp() if item.last_used_at else 0),
                item.name.casefold(),
                item.id,
            )
        )
    else:
        items.sort(key=lambda item: (item.name.casefold(), item.type, item.id))
    return RationSourceListResponse(items=items[:limit])


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


@router.post(
    "/{entry_date}/entries",
    response_model=RationEntryResponse,
    status_code=201,
)
async def create_ration_entry(
    entry_date: date,
    payload: RationEntryCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    grams = parse_entry_grams(payload.grams)

    async def command() -> tuple[int, dict[str, object]]:
        service = diary_service(session)
        source_id = int(payload.source_id)
        if payload.source_type is DiaryEntryType.INGREDIENT:
            entry = await service.add_ingredient(
                user_id=user.id,
                ingredient_id=source_id,
                grams=grams,
                meal_type=payload.meal_type,
                entry_date=entry_date,
            )
        else:
            entry = await service.add_dish(
                user_id=user.id,
                dish_id=source_id,
                grams=grams,
                meal_type=payload.meal_type,
                entry_date=entry_date,
            )
        return 201, entry_response(entry).model_dump(mode="json")

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="ration.entry.create",
        idempotency_key=idempotency_key,
        payload={
            "entry_date": entry_date.isoformat(),
            **payload.model_dump(mode="json"),
        },
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.patch("/entries/{entry_id}", response_model=RationEntryResponse)
async def update_ration_entry(
    entry_id: int,
    payload: RationEntryUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> RationEntryResponse:
    entry = await diary_service(session).update_entry(
        user.id,
        entry_id,
        expected_updated_at=payload.expected_updated_at,
        grams=parse_entry_grams(payload.grams) if payload.grams is not None else None,
        meal_type=payload.meal_type,
        entry_date=payload.entry_date,
    )
    return entry_response(entry)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_ration_entry(
    entry_id: int,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await DiaryRepository(session).delete(entry_id, user.id)
    return Response(status_code=204)


@router.post(
    "/entries/{entry_id}/copy",
    response_model=RationEntryResponse,
    status_code=201,
)
async def copy_ration_entry(
    entry_id: int,
    payload: RationEntryCopyRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    async def command() -> tuple[int, dict[str, object]]:
        entry = await diary_service(session).copy_entry(
            user.id,
            entry_id,
            entry_date=payload.entry_date,
            meal_type=payload.meal_type,
        )
        return 201, entry_response(entry).model_dump(mode="json")

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="ration.entry.copy",
        idempotency_key=idempotency_key,
        payload={"entry_id": str(entry_id), **payload.model_dump(mode="json")},
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )
