from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.reminder import ReminderSetting
from app.exceptions import ValidationError
from app.repositories.account_deletion import AccountDeletionRepository
from app.repositories.diary import DiaryRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.privacy import PrivacyRepository
from app.repositories.reminders import ReminderRepository
from app.repositories.users import UserRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.repositories.weights import WeightRepository
from app.services.account_deletion import (
    DELETION_CONFIRMATION_PHRASE,
    AccountDeletionService,
)
from app.services.nutrition_goals import (
    NutritionGoalData,
    NutritionGoalService,
    parse_nutrition_target,
)
from app.services.privacy import PrivacyService
from app.services.reminders import ReminderService, parse_reminder_time
from app.services.settings import UserSettingsService
from app.services.web_mutations import WebMutationService
from app.utils.datetime import local_today
from app.web.dependencies import CurrentUser, DatabaseSession, IdempotencyKey
from app.web.profile_schemas import (
    DeletionConfirmRequest,
    DeletionRequestResponse,
    NutritionGoalResponse,
    NutritionGoalUpdateRequest,
    OperationResponse,
    ProfileResponse,
    ProfileSettingsUpdateRequest,
    ProfileStatsResponse,
    ReminderCreateRequest,
    ReminderResponse,
    ReminderUpdateRequest,
)

router = APIRouter(prefix="/api/v1")


def privacy_service(request: Request, session: DatabaseSession) -> PrivacyService:
    return PrivacyService(
        PrivacyRepository(session),
        default_timezone=request.app.state.settings.default_timezone,
    )


def reminder_service(session: DatabaseSession) -> ReminderService:
    return ReminderService(
        ReminderRepository(session),
        WeightRepository(session),
        DiaryRepository(session),
        NutritionGoalRepository(session),
    )


def profile_response(
    user: CurrentUser,
    request: Request,
    reminders: list[ReminderSetting],
) -> ProfileResponse:
    return ProfileResponse(
        id=str(user.id),
        telegram_id=str(user.telegram_id),
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        photo_url=getattr(request.state, "telegram_photo_url", None),
        language_code=user.language_code,
        timezone=user.timezone,
        number_format=user.number_format,
        after_food_add_action=user.after_food_add_action,
        confirm_deletions=user.confirm_deletions,
        app_version=request.app.state.settings.app_version,
        reminders_enabled=any(item.enabled for item in reminders),
    )


def nutrition_goal_response(goal: NutritionGoal | None) -> NutritionGoalResponse | None:
    if goal is None:
        return None
    return NutritionGoalResponse(
        id=str(goal.id),
        energy_kcal=str(goal.kcal_target) if goal.kcal_target is not None else None,
        protein_g=(
            str(goal.protein_target_g) if goal.protein_target_g is not None else None
        ),
        fat_g=str(goal.fat_target_g) if goal.fat_target_g is not None else None,
        carbs_g=str(goal.carbs_target_g) if goal.carbs_target_g is not None else None,
        effective_from=goal.effective_from,
        effective_to=goal.effective_to,
    )


def reminder_response(setting: ReminderSetting) -> ReminderResponse:
    return ReminderResponse(
        id=str(setting.id),
        type=setting.reminder_type,
        enabled=setting.enabled,
        time_local=setting.time_local.strftime("%H:%M"),
        weekdays=[
            weekday for weekday in range(7) if setting.weekdays_mask & (1 << weekday)
        ],
        updated_at=setting.updated_at,
    )


def weekdays_mask(weekdays: list[int]) -> int:
    return sum(1 << weekday for weekday in weekdays)


def parse_goal_value(field: str, value: str | None) -> Decimal | None:
    return None if value is None else parse_nutrition_target(field, value)


def mutation_service(request: Request, session: DatabaseSession) -> WebMutationService:
    return WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=request.app.state.settings.web_mutation_receipt_ttl_hours,
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> ProfileResponse:
    reminders = await reminder_service(session).list_for_user(user.id)
    return profile_response(user, request, reminders)


@router.patch("/profile/settings", response_model=ProfileResponse)
async def update_profile_settings(
    payload: ProfileSettingsUpdateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> ProfileResponse:
    service = UserSettingsService(UserRepository(session))
    updated = user
    if payload.timezone is not None:
        updated = await service.set_timezone(user.id, payload.timezone)
    if payload.number_format is not None:
        updated = await service.set_number_format(user.id, payload.number_format)
    if payload.after_food_add_action is not None:
        updated = await service.set_after_food_add_action(
            user.id,
            payload.after_food_add_action,
        )
    if payload.confirm_deletions is not None:
        updated = await service.set_confirm_deletions(
            user.id,
            payload.confirm_deletions,
        )
    reminders = await reminder_service(session).list_for_user(user.id)
    return profile_response(updated, request, reminders)


@router.get("/profile/stats", response_model=ProfileStatsResponse)
async def get_profile_stats(
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> ProfileStatsResponse:
    service = privacy_service(request, session)
    stats = await service.profile_stats(user.id)
    summary = await service.summary(user.id)
    return ProfileStatsResponse(
        diary_days=stats.diary_days,
        ingredients=summary.ingredients,
        dishes=summary.dishes,
        diary_entries=summary.diary_entries,
        weight_entries=summary.weight_entries,
        active_weight_goals=summary.active_goals,
        share_packages=summary.share_packages,
        imported_packages=summary.imported_packages,
    )


@router.get("/goals/nutrition", response_model=NutritionGoalResponse | None)
async def get_nutrition_goal(
    user: CurrentUser,
    session: DatabaseSession,
) -> NutritionGoalResponse | None:
    today = local_today(user.timezone)
    goal = await NutritionGoalService(NutritionGoalRepository(session)).get_for_date(
        user.id,
        today,
    )
    return nutrition_goal_response(goal)


@router.put("/goals/nutrition", response_model=NutritionGoalResponse | None)
async def update_nutrition_goal(
    payload: NutritionGoalUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> NutritionGoalResponse | None:
    today = local_today(user.timezone)
    effective_from = payload.effective_from or today
    if effective_from not in {today, today + timedelta(days=1)}:
        raise ValidationError("Цели можно изменить с сегодняшнего или завтрашнего дня.")
    service = NutritionGoalService(NutritionGoalRepository(session))
    if not payload.enabled:
        current = await service.get_for_date(user.id, effective_from)
        if current is not None:
            await service.disable(user.id, current.id, effective_from)
        return None
    goal = await service.set_goal(
        user.id,
        NutritionGoalData(
            kcal_target=parse_goal_value("kcal_target", payload.energy_kcal),
            protein_target_g=parse_goal_value(
                "protein_target_g",
                payload.protein_g,
            ),
            fat_target_g=parse_goal_value("fat_target_g", payload.fat_g),
            carbs_target_g=parse_goal_value("carbs_target_g", payload.carbs_g),
        ),
        effective_from,
    )
    return nutrition_goal_response(goal)


@router.get("/reminders", response_model=list[ReminderResponse])
async def list_reminders(
    user: CurrentUser,
    session: DatabaseSession,
) -> list[ReminderResponse]:
    settings = await reminder_service(session).list_for_user(user.id)
    return [reminder_response(setting) for setting in settings]


@router.post("/reminders", response_model=ReminderResponse, status_code=201)
async def create_reminder(
    payload: ReminderCreateRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    async def command() -> tuple[int, dict[str, object]]:
        setting = await reminder_service(session).configure(
            user_id=user.id,
            reminder_type=payload.type,
            time_local=parse_reminder_time(payload.time_local),
            weekdays_mask=weekdays_mask(payload.weekdays),
        )
        body = reminder_response(setting).model_dump(mode="json")
        return 201, body

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="reminder.create",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(
        result.body,
        status_code=result.status_code,
        headers={"X-Idempotent-Replayed": str(result.replayed).lower()},
    )


@router.patch("/reminders/{setting_id}", response_model=ReminderResponse)
async def update_reminder(
    setting_id: int,
    payload: ReminderUpdateRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> ReminderResponse:
    setting = await reminder_service(session).update(
        setting_id,
        user.id,
        enabled=payload.enabled,
        time_local=(
            parse_reminder_time(payload.time_local)
            if payload.time_local is not None
            else None
        ),
        weekdays_mask=(
            weekdays_mask(payload.weekdays) if payload.weekdays is not None else None
        ),
    )
    return reminder_response(setting)


@router.delete("/reminders/{setting_id}", status_code=204)
async def delete_reminder(
    setting_id: int,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    await reminder_service(session).delete(setting_id, user.id)
    return Response(status_code=204)


@router.get("/account/export")
async def export_account_data(
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    payload = await privacy_service(request, session).export(user.id)
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": "attachment; filename=wtrackerbot-data.json",
        },
    )


@router.post("/account/deletion-request", response_model=DeletionRequestResponse)
async def request_account_deletion(
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    async def command() -> tuple[int, dict[str, object]]:
        challenge = await AccountDeletionService(
            AccountDeletionRepository(session),
            privacy_service(request, session),
        ).request(user.id)
        body = DeletionRequestResponse(
            confirmation_token=challenge.token,
            confirmation_phrase=DELETION_CONFIRMATION_PHRASE,
            expires_at=challenge.expires_at,
        ).model_dump(mode="json")
        return 200, body

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="account.deletion_request",
        idempotency_key=idempotency_key,
        payload={},
        command=command,
    )
    return JSONResponse(result.body, status_code=result.status_code)


@router.post("/account/deletion-confirm", response_model=OperationResponse)
async def confirm_account_deletion(
    payload: DeletionConfirmRequest,
    request: Request,
    user: CurrentUser,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> Response:
    async def command() -> tuple[int, dict[str, object]]:
        await AccountDeletionService(
            AccountDeletionRepository(session),
            privacy_service(request, session),
        ).confirm(
            user.id,
            token=payload.confirmation_token,
            phrase=payload.confirmation_phrase,
        )
        return 200, {"status": "deleted"}

    result = await mutation_service(request, session).execute(
        user_id=user.id,
        operation="account.deletion_confirm",
        idempotency_key=idempotency_key,
        payload=payload.model_dump(mode="json"),
        command=command,
    )
    return JSONResponse(result.body, status_code=result.status_code)
