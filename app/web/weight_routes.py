from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from app.db.models.weight import WeightEntry
from app.repositories.goals import GoalRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.repositories.weights import WeightRepository
from app.services.goals import GoalDetails, GoalService
from app.services.web_mutations import WebMutationService
from app.services.weight_chart import (
    WeightChartData,
    WeightChartPoint,
    WeightChartService,
    custom_chart_range,
)
from app.services.weights import WeightService, parse_weight
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.weight_schemas import (
    WeightChartPointResponse,
    WeightEntryCreateRequest,
    WeightEntryResponse,
    WeightEntryUpdateRequest,
    WeightGoalProgressResponse,
    WeightGoalResponse,
    WeightGoalUpdateRequest,
    WeightRangeResponse,
)

router = APIRouter(prefix="/api/v1")


def weight_service(session: DatabaseSession) -> WeightService:
    return WeightService(WeightRepository(session))


def goal_service(session: DatabaseSession) -> GoalService:
    return GoalService(GoalRepository(session), WeightRepository(session))


def mutation_service(request: Request, session: DatabaseSession) -> WebMutationService:
    return WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    )


def localize_measured_at(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=ZoneInfo(timezone_name))
    return value


def entry_response(entry: WeightEntry) -> WeightEntryResponse:
    return WeightEntryResponse(
        id=str(entry.id),
        weight_kg=str(entry.weight_kg),
        measured_at=entry.measured_at.astimezone(UTC),
        note=entry.note,
        updated_at=entry.updated_at.astimezone(UTC),
    )


def point_entry_response(point: WeightChartPoint) -> WeightEntryResponse:
    if point.entry_id is None or point.updated_at is None:
        raise RuntimeError("Persisted chart point is missing entry metadata")
    return WeightEntryResponse(
        id=str(point.entry_id),
        weight_kg=str(point.weight_kg),
        measured_at=point.measured_at.astimezone(UTC),
        note=point.note,
        updated_at=point.updated_at.astimezone(UTC),
    )


def goal_response(details: GoalDetails | None) -> WeightGoalResponse | None:
    if details is None:
        return None
    goal = details.goal
    progress = details.progress
    return WeightGoalResponse(
        id=str(goal.id),
        target_weight_kg=str(goal.target_weight_kg),
        start_weight_kg=(
            str(goal.start_weight_kg) if goal.start_weight_kg is not None else None
        ),
        target_date=goal.target_date,
        current_weight_kg=(
            str(details.current_weight.weight_kg)
            if details.current_weight is not None
            else None
        ),
        progress=(
            WeightGoalProgressResponse(
                percentage=str(progress.percentage),
                completed_kg=str(progress.completed_kg),
                remaining_kg=str(progress.remaining_kg),
                achieved=progress.achieved,
            )
            if progress is not None
            else None
        ),
        updated_at=goal.updated_at.astimezone(UTC),
    )


def range_response(
    data: WeightChartData,
    latest: list[WeightEntry],
    goal: GoalDetails | None,
    timezone_name: str,
) -> WeightRangeResponse:
    averages = data.moving_average_7d
    points = [
        WeightChartPointResponse(
            **point_entry_response(point).model_dump(),
            moving_average_7d_kg=(
                str(averages[index]) if averages[index] is not None else None
            ),
        )
        for index, point in enumerate(data.points)
    ]
    current = latest[0] if latest else None
    previous = latest[1] if len(latest) > 1 else None
    return WeightRangeResponse(
        timezone=timezone_name,
        date_from=data.period.date_from,
        date_to=data.period.date_to,
        current=entry_response(current) if current else None,
        previous=entry_response(previous) if previous else None,
        change_from_previous_kg=(
            str(current.weight_kg - previous.weight_kg)
            if current is not None and previous is not None
            else None
        ),
        period_change_kg=(str(data.change_kg) if data.change_kg is not None else None),
        minimum_kg=(str(data.minimum_kg) if data.minimum_kg is not None else None),
        maximum_kg=(str(data.maximum_kg) if data.maximum_kg is not None else None),
        goal=goal_response(goal),
        points=points,
        history=[point_entry_response(point) for point in reversed(data.points)],
    )


@router.get("/weight", response_model=WeightRangeResponse)
async def get_weight_range(
    user: CurrentUser,
    session: DatabaseSession,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> WeightRangeResponse:
    period = custom_chart_range(date_from, date_to)
    repository = WeightRepository(session)
    data = await WeightChartService(repository, GoalRepository(session)).get_data(
        user_id=user.id,
        period=period,
        timezone_name=user.timezone,
    )
    latest = await repository.list(user.id, limit=2, offset=0)
    goal = await goal_service(session).get_active(user.id)
    return range_response(data, latest, goal, user.timezone)


@router.post("/weight", response_model=WeightEntryResponse, status_code=201)
async def create_weight_entry(
    payload: WeightEntryCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    async def command() -> tuple[int, dict[str, object]]:
        entry = await weight_service(session).create(
            user_id=user.id,
            weight_kg=parse_weight(payload.weight_kg),
            measured_at=localize_measured_at(payload.measured_at, user.timezone),
            note=payload.note,
        )
        return 201, entry_response(entry).model_dump(mode="json")

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="weight.entry.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.patch("/weight/{entry_id}", response_model=WeightEntryResponse)
async def update_weight_entry(
    entry_id: int,
    payload: WeightEntryUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> WeightEntryResponse:
    entry = await weight_service(session).update_entry(
        user.id,
        entry_id,
        expected_updated_at=payload.expected_updated_at,
        weight_kg=(
            parse_weight(payload.weight_kg) if payload.weight_kg is not None else None
        ),
        measured_at=(
            localize_measured_at(payload.measured_at, user.timezone)
            if payload.measured_at is not None
            else None
        ),
        note=payload.note,
        note_provided="note" in payload.model_fields_set,
    )
    return entry_response(entry)


@router.delete("/weight/{entry_id}", status_code=204)
async def delete_weight_entry(
    entry_id: int,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await WeightRepository(session).delete(entry_id, user.id)
    return Response(status_code=204)


@router.get("/goals/weight", response_model=WeightGoalResponse | None)
async def get_weight_goal(
    user: CurrentUser,
    session: DatabaseSession,
) -> WeightGoalResponse | None:
    return goal_response(await goal_service(session).get_active(user.id))


@router.put("/goals/weight", response_model=WeightGoalResponse | None)
async def update_weight_goal(
    payload: WeightGoalUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> WeightGoalResponse | None:
    service = goal_service(session)
    active = await service.get_active(user.id)
    if not payload.enabled:
        if active is not None:
            await service.cancel(user.id, active.goal.id)
        return None
    target = parse_weight(payload.target_weight_kg or "")
    if (
        active is not None
        and active.goal.target_weight_kg == target
        and active.goal.target_date == payload.target_date
    ):
        return goal_response(active)
    details = await service.create(
        user_id=user.id,
        target_weight_kg=target,
        target_date=payload.target_date,
        replace_existing=active is not None,
    )
    return goal_response(details)
