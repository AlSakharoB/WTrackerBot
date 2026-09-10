from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.repositories.food_folders import FoodFolderRecord, FoodFolderRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.services.food_folders import FoodFolderService
from app.services.web_mutations import WebMutationService
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.folder_schemas import (
    FoodFolderCreateRequest,
    FoodFolderListResponse,
    FoodFolderReorderRequest,
    FoodFolderResponse,
    FoodFolderUpdateRequest,
    FoodItemFolderBatchRequest,
    FoodItemFolderRequest,
    FoodItemFolderResponse,
    FoodItemType,
)

router = APIRouter(prefix="/api/v1")


def _response(record: FoodFolderRecord) -> FoodFolderResponse:
    folder = record.folder
    return FoodFolderResponse(
        id=str(folder.id),
        name=folder.name,
        sort_order=folder.sort_order,
        item_count=record.item_count,
        ingredient_count=record.ingredient_count,
        dish_count=record.dish_count,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
    )


async def _record(
    repository: FoodFolderRepository, user_id: int, folder_id: int
) -> FoodFolderRecord:
    return next(
        record
        for record in await repository.list(user_id)
        if record.folder.id == folder_id
    )


@router.get("/food-folders", response_model=FoodFolderListResponse)
async def list_folders(
    user: CurrentUser, session: DatabaseSession
) -> FoodFolderListResponse:
    records = await FoodFolderRepository(session).list(user.id)
    return FoodFolderListResponse(items=[_response(record) for record in records])


@router.post("/food-folders", response_model=FoodFolderResponse, status_code=201)
async def create_folder(
    payload: FoodFolderCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    repository = FoodFolderRepository(session)

    async def command() -> tuple[int, dict[str, object]]:
        folder = await FoodFolderService(repository).create(user.id, payload.name)
        response = _response(await _record(repository, user.id, folder.id))
        return 201, response.model_dump(mode="json")

    result = await WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    ).execute(
        user_id=user.id,
        operation="food.folder.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.patch("/food-folders/{folder_id}", response_model=FoodFolderResponse)
async def rename_folder(
    folder_id: int,
    payload: FoodFolderUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> FoodFolderResponse:
    repository = FoodFolderRepository(session)
    folder = await FoodFolderService(repository).rename(
        user.id, folder_id, payload.name
    )
    return _response(await _record(repository, user.id, folder.id))


@router.delete("/food-folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: int, user: CurrentUser, session: DatabaseSession
) -> Response:
    await FoodFolderService(FoodFolderRepository(session)).delete(user.id, folder_id)
    return Response(status_code=204)


@router.post("/food-folders/reorder", response_model=FoodFolderListResponse)
async def reorder_folders(
    payload: FoodFolderReorderRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> FoodFolderListResponse:
    repository = FoodFolderRepository(session)
    await FoodFolderService(repository).reorder(
        user.id, [int(value) for value in payload.folder_ids]
    )
    return FoodFolderListResponse(
        items=[_response(record) for record in await repository.list(user.id)]
    )


@router.put(
    "/food-items/{item_type}/{item_id}/folder",
    response_model=FoodItemFolderResponse,
)
async def move_food_item(
    item_type: FoodItemType,
    item_id: int,
    payload: FoodItemFolderRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> FoodItemFolderResponse:
    await FoodFolderService(FoodFolderRepository(session)).move(
        user.id,
        item_type=item_type,
        item_ids=[item_id],
        folder_id=int(payload.folder_id) if payload.folder_id else None,
    )
    return FoodItemFolderResponse(
        type=item_type, item_ids=[str(item_id)], folder_id=payload.folder_id
    )


@router.post("/food-items/folder-batch", response_model=FoodItemFolderResponse)
async def move_food_items(
    payload: FoodItemFolderBatchRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> FoodItemFolderResponse:
    await FoodFolderService(FoodFolderRepository(session)).move(
        user.id,
        item_type=payload.type,
        item_ids=[int(value) for value in payload.item_ids],
        folder_id=int(payload.folder_id) if payload.folder_id else None,
    )
    return FoodItemFolderResponse(
        type=payload.type,
        item_ids=payload.item_ids,
        folder_id=payload.folder_id,
    )
