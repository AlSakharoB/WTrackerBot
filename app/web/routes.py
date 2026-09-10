import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.config import Settings
from app.core.health import ensure_database_revision_current
from app.db.session import check_database_connection
from app.repositories.ui_preferences import UIPreferenceRepository
from app.services.ui_preferences import UIPreferenceService
from app.web.dependencies import CurrentUser, DatabaseSession
from app.web.profile_routes import router as profile_router
from app.web.ration_routes import router as ration_router
from app.web.schemas import (
    CurrentUserResponse,
    HealthResponse,
    ReadinessResponse,
    UIPreferencesResponse,
    UIPreferencesUpdateRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(profile_router)
router.include_router(ration_router)


@router.get("/internal/healthz", response_model=HealthResponse)
async def healthcheck(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(status="ok", version=settings.app_version)


@router.get(
    "/internal/readyz",
    response_model=ReadinessResponse,
    responses={503: {"model": HealthResponse}},
)
async def readiness(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    engine = request.app.state.database_engine
    try:
        await check_database_connection(engine)
        revision = await ensure_database_revision_current(engine)
    except Exception as error:
        logger.warning(
            "Web readiness check failed",
            exc_info=True,
            extra={
                "operation": "web.readiness",
                "exception_type": type(error).__name__,
            },
        )
        return JSONResponse(
            {"status": "error", "version": settings.app_version},
            status_code=503,
        )
    return JSONResponse(
        ReadinessResponse(
            status="ok",
            version=settings.app_version,
            database_revision=",".join(revision.current),
        ).model_dump()
    )


@router.get("/api/v1/me", response_model=CurrentUserResponse)
async def current_user(user: CurrentUser, request: Request) -> CurrentUserResponse:
    settings: Settings = request.app.state.settings
    return CurrentUserResponse(
        id=str(user.id),
        telegram_id=str(user.telegram_id),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        timezone=user.timezone,
        app_version=settings.app_version,
    )


@router.get("/api/v1/ui-preferences", response_model=UIPreferencesResponse)
async def get_ui_preferences(
    user: CurrentUser,
    session: DatabaseSession,
) -> UIPreferencesResponse:
    preference = await UIPreferenceService(UIPreferenceRepository(session)).get(user.id)
    return UIPreferencesResponse.model_validate(preference, from_attributes=True)


@router.patch("/api/v1/ui-preferences", response_model=UIPreferencesResponse)
async def update_ui_preferences(
    payload: UIPreferencesUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> UIPreferencesResponse:
    preference = await UIPreferenceService(UIPreferenceRepository(session)).update(
        user.id,
        theme_mode=payload.theme_mode,
        default_section=payload.default_section,
        default_weight_unit=payload.default_weight_unit,
        compact_lists=payload.compact_lists,
    )
    return UIPreferencesResponse.model_validate(preference, from_attributes=True)
