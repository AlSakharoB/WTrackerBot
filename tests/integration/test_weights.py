from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.repositories.goals import GoalRepository
from app.repositories.users import UserRepository
from app.repositories.weights import WeightRepository
from app.services.users import TelegramUserData, UserService
from app.services.weight_chart import WeightChartService, custom_chart_range
from app.services.weights import WeightService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Weight Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


async def test_weight_crud_summary_and_ordering(session: AsyncSession) -> None:
    user_id = await create_user(session, 9550000001)
    service = WeightService(WeightRepository(session))
    first = await service.create(
        user_id=user_id,
        weight_kg=Decimal("91.2"),
        measured_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
    )
    middle = await service.create(
        user_id=user_id,
        weight_kg=Decimal("85"),
        measured_at=datetime(2026, 8, 5, 8, tzinfo=UTC),
    )
    current = await service.create(
        user_id=user_id,
        weight_kg=Decimal("82.4"),
        measured_at=datetime(2026, 8, 11, 8, tzinfo=UTC),
    )

    summary = await service.get_summary(user_id)
    assert summary.first is not None
    assert summary.current is not None
    assert summary.first.id == first.id
    assert summary.current.id == current.id
    assert summary.difference_kg == Decimal("-8.80")
    assert [entry.id for entry in summary.recent] == [
        current.id,
        middle.id,
        first.id,
    ]

    updated = await service.update_weight(user_id, current.id, Decimal("81.75"))
    assert updated.weight_kg == Decimal("81.75")
    moved = await service.update_measured_at(
        user_id,
        current.id,
        datetime(2026, 7, 31, 8, tzinfo=UTC),
    )
    assert moved.measured_at == datetime(2026, 7, 31, 8, tzinfo=UTC)
    reordered = await service.get_summary(user_id)
    assert reordered.first is not None
    assert reordered.current is not None
    assert reordered.first.id == current.id
    assert reordered.current.id == middle.id

    await service.delete(user_id, middle.id)
    with pytest.raises(NotFoundError):
        await service.get(user_id, middle.id)


async def test_weight_history_is_paginated_and_isolated(
    session: AsyncSession,
) -> None:
    owner_id = await create_user(session, 9550000002)
    other_id = await create_user(session, 9550000003)
    service = WeightService(WeightRepository(session))
    entries = []
    for day in range(1, 10):
        entries.append(
            await service.create(
                user_id=owner_id,
                weight_kg=Decimal("80") + Decimal(day) / 10,
                measured_at=datetime(2026, 8, day, 8, tzinfo=UTC),
            )
        )

    first_page = await service.list_page(owner_id, 1)
    second_page = await service.list_page(owner_id, 2)
    assert first_page.total == 9
    assert first_page.pages == 2
    assert len(first_page.items) == 8
    assert first_page.items[0].id == entries[-1].id
    assert len(second_page.items) == 1

    with pytest.raises(NotFoundError):
        await service.get(other_id, entries[0].id)
    with pytest.raises(NotFoundError):
        await service.update_weight(other_id, entries[0].id, Decimal("70"))
    with pytest.raises(NotFoundError):
        await service.delete(other_id, entries[0].id)


async def test_weight_chart_range_is_timezone_aware_and_isolated(
    session: AsyncSession,
) -> None:
    owner_id = await create_user(session, 9550000004)
    other_id = await create_user(session, 9550000005)
    weights = WeightService(WeightRepository(session))
    included = await weights.create(
        user_id=owner_id,
        weight_kg=Decimal("82.4"),
        measured_at=datetime(2026, 8, 1, 21, 30, tzinfo=UTC),
    )
    await weights.create(
        user_id=owner_id,
        weight_kg=Decimal("82.1"),
        measured_at=datetime(2026, 8, 2, 21, 30, tzinfo=UTC),
    )
    await weights.create(
        user_id=other_id,
        weight_kg=Decimal("70"),
        measured_at=datetime(2026, 8, 2, 8, tzinfo=UTC),
    )

    data = await WeightChartService(
        WeightRepository(session),
        GoalRepository(session),
    ).get_data(
        user_id=owner_id,
        period=custom_chart_range(date(2026, 8, 2), date(2026, 8, 2)),
        timezone_name="Europe/Moscow",
    )

    assert len(data.points) == 1
    assert data.points[0].weight_kg == included.weight_kg
    assert data.points[0].measured_at.date() == date(2026, 8, 2)
    assert data.target_weight_kg is None
