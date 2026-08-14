from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DiaryEntry,
    DiaryEntryType,
    Dish,
    GoalStatus,
    Ingredient,
    MealType,
    User,
    WeightEntry,
    WeightGoal,
)
from app.repositories.admin import AdminRepository


async def test_admin_repository_returns_global_aggregates(
    session: AsyncSession,
) -> None:
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    repository = AdminRepository(session)
    users_before = await repository.get_user_stats(now)
    entities_before = await repository.get_entity_stats()

    recent_user = User(
        telegram_id=9910000001,
        first_name="Recent",
        timezone="Europe/Moscow",
        created_at=now - timedelta(hours=1),
    )
    old_user = User(
        telegram_id=9910000002,
        first_name="Old",
        timezone="Europe/Moscow",
        created_at=now - timedelta(days=10),
    )
    session.add_all([recent_user, old_user])
    await session.flush()

    ingredient = Ingredient(
        user_id=recent_user.id,
        name="Admin ingredient",
        name_normalized="admin ingredient",
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("15"),
    )
    dish = Dish(
        user_id=recent_user.id,
        name="Admin dish",
        name_normalized="admin dish",
    )
    session.add_all([ingredient, dish])
    await session.flush()
    session.add_all(
        [
            DiaryEntry(
                user_id=recent_user.id,
                entry_date=date(2026, 8, 14),
                entry_type=DiaryEntryType.INGREDIENT,
                ingredient_id=ingredient.id,
                source_name=ingredient.name,
                grams=Decimal("100"),
                meal_type=MealType.LUNCH,
                kcal_snapshot=Decimal("100"),
                protein_snapshot=Decimal("10"),
                fat_snapshot=Decimal("5"),
                carbs_snapshot=Decimal("15"),
            ),
            WeightEntry(
                user_id=recent_user.id,
                weight_kg=Decimal("80"),
                measured_at=now,
            ),
            WeightGoal(
                user_id=recent_user.id,
                target_weight_kg=Decimal("75"),
                start_weight_kg=Decimal("80"),
                status=GoalStatus.ACTIVE,
            ),
        ]
    )
    await session.flush()

    users_after = await repository.get_user_stats(now)
    entities_after = await repository.get_entity_stats()
    database = await repository.get_database_info()

    assert users_after.total == users_before.total + 2
    assert users_after.new_today == users_before.new_today + 1
    assert users_after.new_last_7_days == users_before.new_last_7_days + 1
    assert entities_after.ingredients == entities_before.ingredients + 1
    assert entities_after.dishes == entities_before.dishes + 1
    assert entities_after.diary_entries == entities_before.diary_entries + 1
    assert entities_after.weight_entries == entities_before.weight_entries + 1
    assert entities_after.active_weight_goals == entities_before.active_weight_goals + 1
    assert database.postgresql_version
    assert database.database_size
