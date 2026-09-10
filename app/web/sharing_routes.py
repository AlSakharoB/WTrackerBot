from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.db.models.share import ShareImportStatus
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import ShareRepository
from app.services.nutrition import NutritionValues
from app.services.sharing import InvalidShareLinkError, SharingService
from app.sharing.payloads import (
    DishSharePayload,
    IngredientSharePayload,
    SharePayloadLimits,
)
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.food_routes import (
    _ingredient_response,
    _mutation_service,
    _nutrition_response,
)
from app.web.food_schemas import (
    SharingDishPreview,
    SharingImportRequest,
    SharingImportResponse,
    SharingIngredientPreview,
    SharingPackageCreateRequest,
    SharingPackageResponse,
    SharingPreviewResponse,
)

router = APIRouter(prefix="/api/v1/sharing/packages")


def _shared_nutrition(item) -> NutritionValues:
    return NutritionValues(
        kcal=item.kcal_per_100g,
        protein=item.protein_per_100g,
        fat=item.fat_per_100g,
        carbs=item.carbs_per_100g,
    )


def _service(request: Request, session: DatabaseSession) -> SharingService:
    settings = request.app.state.settings
    return SharingService(
        ShareRepository(session),
        bot_username=settings.bot_username,
        link_ttl_days=settings.share_link_ttl_days,
        limits=SharePayloadLimits(
            max_items=settings.share_max_items,
            max_ingredients=settings.share_max_ingredients,
            max_components=settings.share_max_components,
            max_payload_bytes=settings.share_max_payload_bytes,
        ),
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )


@router.post("", response_model=SharingPackageResponse, status_code=201)
async def create_package(
    payload: SharingPackageCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    service = _service(request, session)
    ids = [int(item) for item in payload.item_ids]

    async def command() -> tuple[int, dict[str, object]]:
        if payload.type == "ingredients":
            result = (
                await service.create_ingredient_package(user.id, ids[0])
                if len(ids) == 1
                else await service.create_ingredient_batch_package(user.id, ids)
            )
        else:
            result = (
                await service.create_dish_package(user.id, ids[0])
                if len(ids) == 1
                else await service.create_dish_batch_package(user.id, ids)
            )
        body = SharingPackageResponse(
            id=str(result.package.id),
            type=result.package.package_type,
            item_count=result.package.item_count,
            deep_link=result.deep_link,
            telegram_share_url=result.telegram_share_url,
            expires_at=result.package.expires_at,
        )
        return 201, body.model_dump(mode="json")

    result = await _mutation_service(request, session).execute(
        user_id=user.id,
        operation="food.share.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


async def _resolve(service: SharingService, token: str, user_id: int):
    try:
        return await service.resolve_ingredient_token(token, user_id)
    except InvalidShareLinkError:
        return await service.resolve_dish_token(token, user_id)


@router.get("/{token}/preview", response_model=SharingPreviewResponse)
async def preview_package(
    token: str,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> SharingPreviewResponse:
    service = _service(request, session)
    access = await _resolve(service, token, user.id)
    imported = (
        access.previous_import is not None
        and access.previous_import.status == ShareImportStatus.COMPLETED
    )
    if isinstance(access.payload, IngredientSharePayload):
        ingredient_preflight = await service.preflight_ingredient_batch(
            user.id, access.payload
        )
        ingredients = [
            SharingIngredientPreview(
                key=item.incoming.key,
                name=item.incoming.name,
                nutrition_per_100g=_nutrition_response(
                    _shared_nutrition(item.incoming)
                ),
                conflict_type=item.conflict_type,
                existing=(
                    _ingredient_response(item.existing)
                    if item.existing is not None
                    else None
                ),
            )
            for item in ingredient_preflight.items
        ]
        dishes = []
        package_type = "ingredients"
    else:
        preflight = await service.preflight_dish_batch(user.id, access.payload)
        ingredients = [
            SharingIngredientPreview(
                key=item.incoming.key,
                name=item.incoming.name,
                nutrition_per_100g=_nutrition_response(
                    _shared_nutrition(item.incoming)
                ),
                conflict_type=item.conflict_type,
                existing=(
                    _ingredient_response(item.existing)
                    if item.existing is not None
                    else None
                ),
            )
            for item in preflight.ingredients.items
        ]
        dishes = [
            SharingDishPreview(
                key=item.dish.key,
                name=item.dish.name,
                conflict_type=item.conflict_type,
                existing_id=str(item.existing.id) if item.existing else None,
            )
            for item in preflight.dishes
        ]
        package_type = "dishes"
    return SharingPreviewResponse(
        package_id=str(access.package.id),
        type=package_type,
        item_count=access.package.item_count,
        is_owner=access.is_owner,
        already_imported=imported,
        expires_at=access.package.expires_at,
        ingredients=ingredients,
        dishes=dishes,
    )


@router.post("/{token}/import", response_model=SharingImportResponse)
async def import_package(
    token: str,
    payload: SharingImportRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> SharingImportResponse:
    service = _service(request, session)
    access = await _resolve(service, token, user.id)
    if isinstance(access.payload, DishSharePayload):
        result = await service.import_dish_batch(
            access.package.id,
            user.id,
            payload.ingredient_decisions,
            payload.dish_decisions,
        )
        record = result.import_record
    else:
        result = await service.import_ingredient_batch(
            access.package.id,
            user.id,
            payload.ingredient_decisions,
        )
        record = result.import_record
    return SharingImportResponse(
        already_imported=result.already_completed,
        created_ingredients=record.created_ingredients_count,
        created_dishes=record.created_dishes_count,
    )


@router.delete("/{package_id}", status_code=204)
async def revoke_package(
    package_id: int,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> None:
    await _service(request, session).revoke_package(package_id, user.id)
