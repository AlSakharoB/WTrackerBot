from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.barcodes import normalize_gtin, safe_off_image_url
from app.integrations.open_food_facts import (
    PROVIDER,
    ExternalProduct,
    ExternalProductInvalidResponse,
    ExternalProductRateLimited,
    ExternalProductUnavailable,
)
from app.repositories.external_products import ExternalProductRepository
from app.repositories.food_folders import FoodFolderRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.services.barcodes import BarcodeLookupService
from app.services.food_folders import FoodFolderService
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientService,
    parse_nutrition_value,
    parse_package_weight,
)
from app.services.web_mutations import WebMutationService
from app.web.barcode_schemas import (
    BarcodeIngredientCreateRequest,
    BarcodeLookupRequest,
    BarcodeLookupResponse,
    BarcodeNutritionResponse,
)
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.errors import WebAPIError
from app.web.food_routes import _ingredient_response

router = APIRouter(prefix="/api/v1/barcodes")


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def _lookup_response(
    product: ExternalProduct, confirmation_token: str
) -> BarcodeLookupResponse:
    nutrition = product.nutrition_per_100g
    return BarcodeLookupResponse(
        barcode=product.barcode,
        found=product.found,
        name=product.name,
        brand=product.brand,
        package_weight_g=_decimal(product.package_weight_g),
        package_quantity=product.package_quantity,
        package_quantity_unit=product.package_quantity_unit,
        serving_size=product.serving_size,
        nutrition_per_100g=BarcodeNutritionResponse(
            energy_kcal=_decimal(nutrition.energy_kcal),
            protein_g=_decimal(nutrition.protein_g),
            fat_g=_decimal(nutrition.fat_g),
            carbs_g=_decimal(nutrition.carbs_g),
        ),
        photo_url=product.photo_url,
        missing_fields=list(product.missing_fields),
        derived_fields=list(product.derived_fields),
        source=PROVIDER,
        source_url=f"https://world.openfoodfacts.org/product/{product.barcode}",
        confirmation_token=confirmation_token,
    )


@router.post("/lookup", response_model=BarcodeLookupResponse)
async def lookup_barcode(
    payload: BarcodeLookupRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> BarcodeLookupResponse:
    barcode = normalize_gtin(payload.barcode)
    decision = await request.app.state.barcode_rate_limiter.check(user.id)
    if not decision.allowed:
        raise WebAPIError(
            "barcode_rate_limited",
            "Слишком много запросов штрихкода. Попробуйте позже.",
            status_code=429,
            headers={"Retry-After": str(decision.retry_after)},
        )
    settings = request.app.state.settings
    service = BarcodeLookupService(
        ExternalProductRepository(session),
        request.app.state.open_food_facts_client,
        positive_cache_seconds=settings.open_food_facts_positive_cache_seconds,
        negative_cache_seconds=settings.open_food_facts_negative_cache_seconds,
    )
    try:
        product = await service.lookup(barcode)
    except ExternalProductRateLimited as error:
        raise WebAPIError(
            "external_rate_limited", str(error), status_code=503
        ) from error
    except (ExternalProductUnavailable, ExternalProductInvalidResponse) as error:
        raise WebAPIError(
            "external_product_unavailable", str(error), status_code=503
        ) from error
    token = request.app.state.barcode_confirmation_signer.issue(user.id, barcode)
    return _lookup_response(product, token)


@router.post("/{barcode}/create-ingredient", status_code=201)
async def create_barcode_ingredient(
    barcode: str,
    payload: BarcodeIngredientCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    normalized_barcode = normalize_gtin(barcode)
    request.app.state.barcode_confirmation_signer.verify(
        payload.confirmation_token, user.id, normalized_barcode
    )
    photo_url = str(payload.photo_url) if payload.photo_url is not None else None
    if photo_url is not None and safe_off_image_url(photo_url) is None:
        raise WebAPIError(
            "invalid_external_image",
            "Фото должно находиться на разрешенном HTTPS-хосте Open Food Facts.",
            status_code=422,
        )
    external_repository = ExternalProductRepository(session)
    ingredient_service = IngredientService(IngredientRepository(session))
    folder_service = FoodFolderService(FoodFolderRepository(session))

    async def command() -> tuple[int, dict[str, object]]:
        await external_repository.lock_source(user.id, PROVIDER, normalized_barcode)
        existing = await external_repository.find_ingredient_by_source(
            user.id, PROVIDER, normalized_barcode
        )
        if existing is not None:
            raise WebAPIError(
                "barcode_already_imported",
                f"Продукт «{existing.name}» с этим штрихкодом уже добавлен.",
                status_code=409,
                details={
                    "existing": _ingredient_response(existing).model_dump(mode="json")
                },
            )
        similar = await ingredient_service.find_similar(user.id, payload.name)
        if similar is not None:
            raise WebAPIError(
                "similar_food_exists",
                f"Похожий ингредиент «{similar.name}» уже существует.",
                status_code=409,
                details={
                    "existing": _ingredient_response(similar).model_dump(mode="json")
                },
            )
        if payload.folder_id is not None:
            await folder_service.get(user.id, int(payload.folder_id))
        ingredient = await ingredient_service.create(
            user.id,
            CreateIngredientData(
                name=payload.name,
                kcal_per_100g=parse_nutrition_value(
                    IngredientField.KCAL, payload.energy_kcal_per_100g
                ),
                protein_per_100g=parse_nutrition_value(
                    IngredientField.PROTEIN, payload.protein_g_per_100g
                ),
                fat_per_100g=parse_nutrition_value(
                    IngredientField.FAT, payload.fat_g_per_100g
                ),
                carbs_per_100g=parse_nutrition_value(
                    IngredientField.CARBS, payload.carbs_g_per_100g
                ),
                package_weight_g=parse_package_weight(payload.package_weight_g),
                photo_url=photo_url,
                source_name="Open Food Facts",
                source_url=(
                    f"https://world.openfoodfacts.org/product/{normalized_barcode}"
                ),
            ),
        )
        snapshot = payload.model_dump(
            mode="json", exclude={"confirmation_token", "confirmed"}
        )
        await external_repository.add_source(
            user_id=user.id,
            ingredient_id=ingredient.id,
            provider=PROVIDER,
            external_code=normalized_barcode,
            source_snapshot_json=snapshot,
        )
        folder_id = int(payload.folder_id) if payload.folder_id else None
        if folder_id is not None:
            await folder_service.move(
                user.id,
                item_type="ingredient",
                item_ids=[ingredient.id],
                folder_id=folder_id,
            )
        return 201, _ingredient_response(ingredient, folder_id).model_dump(mode="json")

    result = await WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    ).execute(
        user_id=user.id,
        operation="barcode.ingredient.create",
        idempotency_key=idempotency_key,
        payload={"barcode": normalized_barcode, **payload.model_dump(mode="json")},
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )
