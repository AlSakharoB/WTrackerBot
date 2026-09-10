from __future__ import annotations

import base64
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app.db.models.ingredient import Ingredient
from app.repositories.dishes import DishRecord, DishRepository
from app.repositories.food_folders import FoodFolderRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.search import normalize_search_text
from app.services.dishes import DishComponentData, DishDetails, DishService
from app.services.food_folders import FoodFolderService
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientService,
    parse_nutrition_value,
    parse_package_weight,
)
from app.services.nutrition import NutritionValues
from app.services.web_mutations import WebMutationService
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.errors import WebAPIError
from app.web.food_schemas import (
    DeleteConsequenceResponse,
    DishComponentResponse,
    DishCreateRequest,
    DishListResponse,
    DishResponse,
    DishUpdateRequest,
    FoodNutritionResponse,
    FoodSort,
    IngredientCreateRequest,
    IngredientListResponse,
    IngredientResponse,
    IngredientUpdateRequest,
)

router = APIRouter(prefix="/api/v1")
PAGE_SIZE = 30


def _nutrition_response(values: NutritionValues) -> FoodNutritionResponse:
    return FoodNutritionResponse(
        energy_kcal=str(values.kcal),
        protein_g=str(values.protein),
        fat_g=str(values.fat),
        carbs_g=str(values.carbs),
    )


def _ingredient_response(
    ingredient: Ingredient, folder_id: int | None = None
) -> IngredientResponse:
    return IngredientResponse(
        id=str(ingredient.id),
        name=ingredient.name,
        folder_id=str(folder_id) if folder_id is not None else None,
        nutrition_per_100g=_nutrition_response(
            NutritionValues(
                kcal=ingredient.kcal_per_100g,
                protein=ingredient.protein_per_100g,
                fat=ingredient.fat_per_100g,
                carbs=ingredient.carbs_per_100g,
            )
        ),
        created_at=ingredient.created_at,
        updated_at=ingredient.updated_at,
        package_weight_g=(
            str(ingredient.package_weight_g)
            if ingredient.package_weight_g is not None
            else None
        ),
        photo_url=ingredient.photo_url,
        source_name=ingredient.source_name,
        source_url=ingredient.source_url,
    )


def _dish_response(details: DishDetails, folder_id: int | None = None) -> DishResponse:
    return DishResponse(
        id=str(details.dish.id),
        name=details.dish.name,
        folder_id=str(folder_id) if folder_id is not None else None,
        total_weight_g=str(details.nutrition.total_weight),
        nutrition_total=_nutrition_response(details.nutrition.total),
        nutrition_per_100g=_nutrition_response(details.nutrition.per_100g),
        components=[
            DishComponentResponse(
                ingredient=_ingredient_response(item.ingredient), grams=str(item.grams)
            )
            for item in details.components
        ],
        created_at=details.dish.created_at,
        updated_at=details.dish.updated_at,
    )


def _cursor_data(cursor: str | None, sort: FoodSort) -> dict[str, Any]:
    if cursor is None:
        return {}
    try:
        padding = "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if data.get("sort") != sort or not isinstance(data.get("id"), int):
            raise ValueError
        if "created_at" in data:
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        return data
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise WebAPIError(
            "invalid_cursor", "Некорректный курсор списка.", status_code=422
        ) from error


def _next_cursor(item: Ingredient | DishRecord, sort: FoodSort) -> str:
    entity = item.dish if isinstance(item, DishRecord) else item
    data: dict[str, object] = {"sort": sort, "id": entity.id}
    if sort in {"newest", "oldest"}:
        data["created_at"] = entity.created_at.isoformat()
    else:
        data["name"] = entity.name_normalized
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _mutation_service(request: Request, session: DatabaseSession) -> WebMutationService:
    return WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    )


def _create_data(payload: IngredientCreateRequest) -> CreateIngredientData:
    return CreateIngredientData(
        name=payload.name,
        kcal_per_100g=parse_nutrition_value(
            IngredientField.KCAL, payload.energy_kcal_per_100g
        ),
        protein_per_100g=parse_nutrition_value(
            IngredientField.PROTEIN, payload.protein_g_per_100g
        ),
        fat_per_100g=parse_nutrition_value(IngredientField.FAT, payload.fat_g_per_100g),
        carbs_per_100g=parse_nutrition_value(
            IngredientField.CARBS, payload.carbs_g_per_100g
        ),
        package_weight_g=parse_package_weight(payload.package_weight_g),
        photo_url=str(payload.photo_url) if payload.photo_url is not None else None,
        source_name=payload.source_name,
        source_url=str(payload.source_url) if payload.source_url is not None else None,
    )


async def _raise_ingredient_duplicate(
    service: IngredientService,
    user_id: int,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    duplicate = await service.find_similar(user_id, name, exclude_id=exclude_id)
    if duplicate is not None:
        raise WebAPIError(
            "similar_food_exists",
            f"Похожий ингредиент «{duplicate.name}» уже существует.",
            status_code=409,
            details={
                "existing": _ingredient_response(duplicate).model_dump(mode="json")
            },
        )


async def _folder_filter(
    repository: FoodFolderRepository, user_id: int, value: str | None
) -> tuple[int | None, bool]:
    if value is None:
        return None, False
    if value == "unfiled":
        return None, True
    if not value.isdigit() or value.startswith("0"):
        raise WebAPIError("folder_not_found", "Папка не найдена.", status_code=404)
    if await repository.get(user_id, int(value)) is None:
        raise WebAPIError("folder_not_found", "Папка не найдена.", status_code=404)
    return int(value), False


@router.get("/ingredients", response_model=IngredientListResponse)
async def list_ingredients(
    user: CurrentUser,
    session: DatabaseSession,
    query: str | None = Query(default=None, max_length=100),
    folder_id: str | None = Query(default=None, max_length=20),
    sort: FoodSort = "name_asc",
    cursor: str | None = Query(default=None, max_length=1024),
) -> IngredientListResponse:
    folder_repository = FoodFolderRepository(session)
    selected_folder_id, unfiled = await _folder_filter(
        folder_repository, user.id, folder_id
    )
    data = _cursor_data(cursor, sort)
    items = await IngredientRepository(session).search_cursor(
        user.id,
        query=normalize_search_text(query or "") or None,
        sort=sort,
        cursor_name=data.get("name"),
        cursor_created_at=data.get("created_at"),
        cursor_id=data.get("id"),
        limit=PAGE_SIZE + 1,
        folder_id=selected_folder_id,
        unfiled=unfiled,
    )
    has_more = len(items) > PAGE_SIZE
    visible = items[:PAGE_SIZE]
    assignments = await folder_repository.ingredient_folder_ids(
        user.id, [item.id for item in visible]
    )
    return IngredientListResponse(
        items=[
            _ingredient_response(item, assignments.get(item.id)) for item in visible
        ],
        next_cursor=_next_cursor(visible[-1], sort) if has_more else None,
    )


@router.post("/ingredients", response_model=IngredientResponse, status_code=201)
async def create_ingredient(
    payload: IngredientCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    service = IngredientService(IngredientRepository(session))
    folder_service = FoodFolderService(FoodFolderRepository(session))

    async def command() -> tuple[int, dict[str, object]]:
        if payload.folder_id is not None:
            await folder_service.get(user.id, int(payload.folder_id))
        await _raise_ingredient_duplicate(service, user.id, payload.name)
        ingredient = await service.create(user.id, _create_data(payload))
        if payload.folder_id is not None:
            await folder_service.move(
                user.id,
                item_type="ingredient",
                item_ids=[ingredient.id],
                folder_id=int(payload.folder_id),
            )
        return 201, _ingredient_response(
            ingredient,
            int(payload.folder_id) if payload.folder_id else None,
        ).model_dump(mode="json")

    result = await _mutation_service(request, session).execute(
        user_id=user.id,
        operation="food.ingredient.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.get("/ingredients/{ingredient_id}", response_model=IngredientResponse)
async def get_ingredient(
    ingredient_id: int, user: CurrentUser, session: DatabaseSession
) -> IngredientResponse:
    ingredient = await IngredientService(IngredientRepository(session)).get(
        user.id, ingredient_id
    )
    assignments = await FoodFolderRepository(session).ingredient_folder_ids(
        user.id, [ingredient.id]
    )
    return _ingredient_response(ingredient, assignments.get(ingredient.id))


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientResponse)
async def update_ingredient(
    ingredient_id: int,
    payload: IngredientUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> IngredientResponse:
    service = IngredientService(IngredientRepository(session))
    ingredient = await service.get(user.id, ingredient_id)
    if payload.name is not None:
        await _raise_ingredient_duplicate(
            service, user.id, payload.name, exclude_id=ingredient_id
        )
    fields = (
        ("name", IngredientField.NAME),
        ("energy_kcal_per_100g", IngredientField.KCAL),
        ("protein_g_per_100g", IngredientField.PROTEIN),
        ("fat_g_per_100g", IngredientField.FAT),
        ("carbs_g_per_100g", IngredientField.CARBS),
    )
    for request_field, domain_field in fields:
        value = getattr(payload, request_field)
        if value is not None:
            ingredient = await service.update_field(
                user.id, ingredient_id, domain_field, value
            )
    metadata_fields: dict[str, str | Decimal | None] = {}
    if "package_weight_g" in payload.model_fields_set:
        metadata_fields["package_weight_g"] = parse_package_weight(
            payload.package_weight_g
        )
    if "photo_url" in payload.model_fields_set:
        metadata_fields["photo_url"] = (
            str(payload.photo_url) if payload.photo_url is not None else None
        )
    if "source_name" in payload.model_fields_set:
        metadata_fields["source_name"] = payload.source_name
    if "source_url" in payload.model_fields_set:
        metadata_fields["source_url"] = (
            str(payload.source_url) if payload.source_url is not None else None
        )
    if metadata_fields:
        ingredient = await IngredientRepository(session).update(
            ingredient_id, user.id, metadata_fields
        )
    folder_repository = FoodFolderRepository(session)
    if "folder_id" in payload.model_fields_set:
        await FoodFolderService(folder_repository).move(
            user.id,
            item_type="ingredient",
            item_ids=[ingredient_id],
            folder_id=int(payload.folder_id) if payload.folder_id else None,
        )
    assert ingredient is not None
    assignments = await folder_repository.ingredient_folder_ids(
        user.id, [ingredient_id]
    )
    return _ingredient_response(ingredient, assignments.get(ingredient_id))


@router.get(
    "/ingredients/{ingredient_id}/delete-consequences",
    response_model=DeleteConsequenceResponse,
)
async def ingredient_delete_consequences(
    ingredient_id: int, user: CurrentUser, session: DatabaseSession
) -> DeleteConsequenceResponse:
    repository = IngredientRepository(session)
    ingredient = await IngredientService(repository).get(user.id, ingredient_id)
    dependencies = await repository.get_usage_dish_names(ingredient.id, user.id)
    return DeleteConsequenceResponse(
        can_delete=not dependencies,
        message=(
            "Ингредиент используется в блюдах. Сначала удалите его из состава."
            if dependencies
            else "Ингредиент будет удален. Записи рациона сохранят снимок КБЖУ."
        ),
        dependencies=dependencies,
    )


@router.delete("/ingredients/{ingredient_id}", status_code=204)
async def delete_ingredient(
    ingredient_id: int, user: CurrentUser, session: DatabaseSession
) -> Response:
    repository = IngredientRepository(session)
    if await repository.get_by_id(ingredient_id, user.id) is not None:
        await IngredientService(repository).delete(user.id, ingredient_id)
    return Response(status_code=204)


def _component_data(
    payload: DishCreateRequest | DishUpdateRequest,
) -> list[DishComponentData]:
    from app.services.dishes import parse_component_grams

    return [
        DishComponentData(
            ingredient_id=int(item.ingredient_id),
            grams=parse_component_grams(item.grams),
        )
        for item in payload.components
    ]


async def _raise_dish_duplicate(
    service: DishService,
    user_id: int,
    name: str,
    *,
    exclude_id: int | None = None,
) -> None:
    duplicate = await service.find_similar(user_id, name, exclude_id=exclude_id)
    if duplicate is not None:
        details = await service.get(user_id, duplicate.id)
        raise WebAPIError(
            "similar_food_exists",
            f"Похожее блюдо «{duplicate.name}» уже существует.",
            status_code=409,
            details={"existing": _dish_response(details).model_dump(mode="json")},
        )


@router.get("/dishes", response_model=DishListResponse)
async def list_dishes(
    user: CurrentUser,
    session: DatabaseSession,
    query: str | None = Query(default=None, max_length=100),
    folder_id: str | None = Query(default=None, max_length=20),
    sort: FoodSort = "name_asc",
    cursor: str | None = Query(default=None, max_length=1024),
) -> DishListResponse:
    folder_repository = FoodFolderRepository(session)
    selected_folder_id, unfiled = await _folder_filter(
        folder_repository, user.id, folder_id
    )
    data = _cursor_data(cursor, sort)
    records = await DishRepository(session).search_records_cursor(
        user.id,
        query=normalize_search_text(query or "") or None,
        sort=sort,
        cursor_name=data.get("name"),
        cursor_created_at=data.get("created_at"),
        cursor_id=data.get("id"),
        limit=PAGE_SIZE + 1,
        folder_id=selected_folder_id,
        unfiled=unfiled,
    )
    visible = records[:PAGE_SIZE]
    service = DishService(DishRepository(session))
    assignments = await folder_repository.dish_folder_ids(
        user.id, [item.dish.id for item in visible]
    )
    return DishListResponse(
        items=[
            _dish_response(
                service._details_from_record(item), assignments.get(item.dish.id)
            )
            for item in visible
        ],
        next_cursor=_next_cursor(visible[-1], sort)
        if len(records) > PAGE_SIZE
        else None,
    )


@router.post("/dishes", response_model=DishResponse, status_code=201)
async def create_dish(
    payload: DishCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    service = DishService(DishRepository(session))
    folder_service = FoodFolderService(FoodFolderRepository(session))

    async def command() -> tuple[int, dict[str, object]]:
        if payload.folder_id is not None:
            await folder_service.get(user.id, int(payload.folder_id))
        await _raise_dish_duplicate(service, user.id, payload.name)
        details = await service.create(user.id, payload.name, _component_data(payload))
        if payload.folder_id is not None:
            await folder_service.move(
                user.id,
                item_type="dish",
                item_ids=[details.dish.id],
                folder_id=int(payload.folder_id),
            )
        return 201, _dish_response(
            details, int(payload.folder_id) if payload.folder_id else None
        ).model_dump(mode="json")

    result = await _mutation_service(request, session).execute(
        user_id=user.id,
        operation="food.dish.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.get("/dishes/{dish_id}", response_model=DishResponse)
async def get_dish(
    dish_id: int, user: CurrentUser, session: DatabaseSession
) -> DishResponse:
    details = await DishService(DishRepository(session)).get(user.id, dish_id)
    assignments = await FoodFolderRepository(session).dish_folder_ids(
        user.id, [dish_id]
    )
    return _dish_response(details, assignments.get(dish_id))


@router.patch("/dishes/{dish_id}", response_model=DishResponse)
async def update_dish(
    dish_id: int,
    payload: DishUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> DishResponse:
    service = DishService(DishRepository(session))
    await service.get(user.id, dish_id)
    await _raise_dish_duplicate(service, user.id, payload.name, exclude_id=dish_id)
    details = await service.replace(
        user.id, dish_id, payload.name, _component_data(payload)
    )
    folder_repository = FoodFolderRepository(session)
    if "folder_id" in payload.model_fields_set:
        await FoodFolderService(folder_repository).move(
            user.id,
            item_type="dish",
            item_ids=[dish_id],
            folder_id=int(payload.folder_id) if payload.folder_id else None,
        )
    assignments = await folder_repository.dish_folder_ids(user.id, [dish_id])
    return _dish_response(details, assignments.get(dish_id))


@router.get(
    "/dishes/{dish_id}/delete-consequences",
    response_model=DeleteConsequenceResponse,
)
async def dish_delete_consequences(
    dish_id: int, user: CurrentUser, session: DatabaseSession
) -> DeleteConsequenceResponse:
    await DishService(DishRepository(session)).get(user.id, dish_id)
    return DeleteConsequenceResponse(
        can_delete=True,
        message="Блюдо будет удалено. Записи рациона сохранят снимок КБЖУ.",
        dependencies=[],
    )


@router.delete("/dishes/{dish_id}", status_code=204)
async def delete_dish(
    dish_id: int, user: CurrentUser, session: DatabaseSession
) -> Response:
    repository = DishRepository(session)
    if await repository.get_by_id(dish_id, user.id) is not None:
        await DishService(repository).delete(user.id, dish_id)
    return Response(status_code=204)
