from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.goal import GoalStatus
from app.exceptions import DuplicateError, NotFoundError
from app.repositories.goals import GoalRepository
from app.repositories.users import UserRepository
from app.repositories.weights import WeightRepository
from app.services.goals import GoalService
from app.services.users import TelegramUserData, UserService
from app.services.weights import WeightService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Goal Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


def goal_service(session: AsyncSession) -> GoalService:
    return GoalService(GoalRepository(session), WeightRepository(session))


async def add_weight(
    session: AsyncSession,
    user_id: int,
    weight: str,
    measured_at: datetime,
) -> None:
    await WeightService(WeightRepository(session)).create(
        user_id=user_id,
        weight_kg=Decimal(weight),
        measured_at=measured_at,
    )


async def test_goal_lifecycle_snapshot_progress_and_replace(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9660000001)
    await add_weight(
        session,
        user_id,
        "90",
        datetime(2026, 8, 1, 8, tzinfo=UTC),
    )
    service = goal_service(session)
    created = await service.create(
        user_id=user_id,
        target_weight_kg=Decimal("80"),
        target_date=date(2026, 12, 15),
    )
    assert created.goal.start_weight_kg == Decimal("90.00")
    assert created.goal.status is GoalStatus.ACTIVE
    assert created.progress is not None
    assert created.progress.percentage == Decimal("0")

    await add_weight(
        session,
        user_id,
        "85",
        datetime(2026, 8, 10, 8, tzinfo=UTC),
    )
    active = await service.get_active(user_id)
    assert active is not None
    assert active.progress is not None
    assert active.goal.start_weight_kg == Decimal("90.00")
    assert active.progress.percentage == Decimal("50.0")
    assert active.progress.remaining_kg == Decimal("5.00")

    with pytest.raises(DuplicateError):
        await service.create(
            user_id=user_id,
            target_weight_kg=Decimal("75"),
            target_date=None,
        )

    replacement = await service.create(
        user_id=user_id,
        target_weight_kg=Decimal("75"),
        target_date=None,
        replace_existing=True,
    )
    old_goal = await GoalRepository(session).get_by_id(created.goal.id, user_id)
    assert old_goal is not None
    assert old_goal.status is GoalStatus.CANCELLED
    assert replacement.goal.start_weight_kg == Decimal("85.00")

    completed = await service.complete(user_id, replacement.goal.id)
    assert completed.status is GoalStatus.COMPLETED
    assert completed.completed_at is not None
    assert await service.get_active(user_id) is None

    next_goal = await service.create(
        user_id=user_id,
        target_weight_kg=Decimal("82"),
        target_date=None,
    )
    cancelled = await service.cancel(user_id, next_goal.goal.id)
    assert cancelled.status is GoalStatus.CANCELLED
    assert await service.get_active(user_id) is None


async def test_goal_without_weight_and_cross_user_isolation(
    session: AsyncSession,
) -> None:
    owner_id = await create_user(session, 9660000002)
    other_id = await create_user(session, 9660000003)
    service = goal_service(session)
    created = await service.create(
        user_id=owner_id,
        target_weight_kg=Decimal("70"),
        target_date=None,
    )

    assert created.goal.start_weight_kg is None
    assert created.current_weight is None
    assert created.progress is None
    assert await service.get_active(other_id) is None

    await add_weight(
        session,
        owner_id,
        "82.5",
        datetime(2026, 8, 12, 8, tzinfo=UTC),
    )
    initialized = await service.get_active(owner_id)
    assert initialized is not None
    assert initialized.goal.start_weight_kg == Decimal("82.50")
    assert initialized.progress is not None
    assert initialized.progress.percentage == Decimal("0")

    persisted = await GoalRepository(session).get_by_id(created.goal.id, owner_id)
    assert persisted is not None
    assert persisted.start_weight_kg == Decimal("82.50")

    with pytest.raises(NotFoundError):
        await service.complete(other_id, created.goal.id)
    with pytest.raises(NotFoundError):
        await service.cancel(other_id, created.goal.id)

    with pytest.raises(DuplicateError):
        await GoalRepository(session).create(
            user_id=owner_id,
            target_weight_kg=Decimal("65"),
            target_date=None,
            start_weight_kg=None,
        )
