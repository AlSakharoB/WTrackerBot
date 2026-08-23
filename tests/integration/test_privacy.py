from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.dish import Dish, DishIngredient
from app.db.models.goal import GoalStatus, WeightGoal
from app.db.models.ingredient import Ingredient
from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.reminder import ReminderSetting, ReminderType
from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)
from app.db.models.user import User
from app.db.models.weight import WeightEntry
from app.repositories.privacy import PrivacyRepository
from app.repositories.users import UserRepository
from app.services.privacy import PrivacyService, UserDataSummary
from app.services.settings import UserSettingsService
from app.services.users import TelegramUserData, UserService
from app.user_settings import AfterFoodAddAction, NumberFormat


def telegram_data(telegram_id: int) -> TelegramUserData:
    return TelegramUserData(
        telegram_id=telegram_id,
        username=f"user_{telegram_id}",
        first_name="Privacy Test",
        last_name=None,
        language_code="ru",
    )


async def create_user(session: AsyncSession, telegram_id: int) -> User:
    return (
        await UserService(
            UserRepository(session),
            default_timezone="Europe/Moscow",
        ).sync_telegram_user(telegram_data(telegram_id))
    ).user


async def add_all_user_data(session: AsyncSession, user: User, suffix: str) -> None:
    ingredient = Ingredient(
        user_id=user.id,
        name=f"Ingredient {suffix}",
        name_normalized=f"ingredient {suffix}",
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("15"),
    )
    session.add(ingredient)
    await session.flush()
    dish = Dish(
        user_id=user.id,
        name=f"Dish {suffix}",
        name_normalized=f"dish {suffix}",
    )
    session.add(dish)
    await session.flush()
    session.add_all(
        [
            DishIngredient(
                dish_id=dish.id,
                ingredient_id=ingredient.id,
                grams=Decimal("100"),
            ),
            DiaryEntry(
                user_id=user.id,
                entry_date=date(2026, 8, 14),
                entry_type=DiaryEntryType.INGREDIENT,
                ingredient_id=ingredient.id,
                dish_id=None,
                source_name=ingredient.name,
                grams=Decimal("100"),
                meal_type=MealType.LUNCH,
                kcal_snapshot=Decimal("100"),
                protein_snapshot=Decimal("10"),
                fat_snapshot=Decimal("5"),
                carbs_snapshot=Decimal("15"),
            ),
            WeightEntry(
                user_id=user.id,
                weight_kg=Decimal("80"),
                measured_at=datetime(2026, 8, 14, 8, tzinfo=UTC),
            ),
            WeightGoal(
                user_id=user.id,
                target_weight_kg=Decimal("75"),
                start_weight_kg=Decimal("80"),
                target_date=None,
                status=GoalStatus.ACTIVE,
            ),
            NutritionGoal(
                user_id=user.id,
                kcal_target=Decimal("2000"),
                protein_target_g=None,
                fat_target_g=None,
                carbs_target_g=None,
                effective_from=date(2026, 8, 1),
            ),
            ReminderSetting(
                user_id=user.id,
                reminder_type=ReminderType.WEIGH_IN,
                enabled=True,
                time_local=datetime.strptime("08:00", "%H:%M").time(),
                weekdays_mask=0b1111111,
            ),
        ]
    )
    await session.flush()


def privacy_service(repository: PrivacyRepository) -> PrivacyService:
    return PrivacyService(repository, default_timezone="Europe/Moscow")


async def test_summary_and_full_delete_keep_user_and_isolate_accounts(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, 9780000001)
    other = await create_user(session, 9780000002)
    await add_all_user_data(session, owner, "owner")
    await add_all_user_data(session, other, "other")
    await UserSettingsService(UserRepository(session)).set_timezone(
        owner.id, "Europe/London"
    )
    await UserSettingsService(UserRepository(session)).set_number_format(
        owner.id, NumberFormat.TWO_DECIMALS
    )
    await UserSettingsService(UserRepository(session)).set_after_food_add_action(
        owner.id, AfterFoodAddAction.STAY
    )
    service = privacy_service(PrivacyRepository(session))

    assert await service.summary(owner.id) == UserDataSummary(1, 1, 1, 1, 1)
    await service.clear_user_data(owner.id)

    assert await service.summary(owner.id) == UserDataSummary(0, 0, 0, 0, 0)
    assert await service.summary(other.id) == UserDataSummary(1, 1, 1, 1, 1)
    owner_after = await UserRepository(session).get_by_id(owner.id)
    assert owner_after is not None
    assert owner_after.telegram_id == owner.telegram_id
    assert owner_after.timezone == "Europe/Moscow"
    assert owner_after.number_format == NumberFormat.AUTOMATIC.value
    assert owner_after.after_food_add_action == AfterFoodAddAction.OPEN_TODAY.value
    component_count = await session.scalar(select(func.count(DishIngredient.id)))
    assert component_count == 1
    nutrition_goal_count = await session.scalar(select(func.count(NutritionGoal.id)))
    assert nutrition_goal_count == 1
    reminder_count = await session.scalar(select(func.count(ReminderSetting.id)))
    assert reminder_count == 1

    sync = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(telegram_data(owner.telegram_id))
    assert sync.created is False
    assert sync.user.id == owner.id


async def test_delete_rolls_back_all_steps_on_mid_operation_error(
    session: AsyncSession,
) -> None:
    user = await create_user(session, 9780000003)
    await add_all_user_data(session, user, "rollback")
    repository = PrivacyRepository(session)
    repository.delete_weight_entries = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("forced failure")
    )
    service = privacy_service(repository)

    with pytest.raises(RuntimeError, match="forced failure"):
        await service.clear_user_data(user.id)

    assert await service.summary(user.id) == UserDataSummary(1, 1, 1, 1, 1)
    component_count = await session.scalar(select(func.count(DishIngredient.id)))
    assert component_count == 1
    nutrition_goal_count = await session.scalar(select(func.count(NutritionGoal.id)))
    assert nutrition_goal_count == 1
    reminder_count = await session.scalar(select(func.count(ReminderSetting.id)))
    assert reminder_count == 1


async def test_privacy_delete_removes_sharing_metadata_not_recipient_owned_rows(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, 9780000004)
    recipient = await create_user(session, 9780000005)
    imported_ingredient = Ingredient(
        user_id=recipient.id,
        name="Imported",
        name_normalized="imported",
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("15"),
    )
    session.add(imported_ingredient)
    package = SharePackage(
        owner_user_id=owner.id,
        token_hash="a" * 64,
        package_type=SharePackageType.INGREDIENTS,
        payload_version=1,
        payload={"version": 1, "type": "ingredients", "ingredients": []},
        item_count=1,
        status=SharePackageStatus.ACTIVE,
        expires_at=datetime.now(UTC),
    )
    session.add(package)
    await session.flush()
    session.add(
        ShareImport(
            package_id=package.id,
            recipient_user_id=recipient.id,
            status=ShareImportStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
    )
    await session.flush()

    owner_summary = await privacy_service(PrivacyRepository(session)).summary(owner.id)
    recipient_summary = await privacy_service(PrivacyRepository(session)).summary(
        recipient.id
    )
    assert owner_summary.share_packages == 1
    assert recipient_summary.imported_packages == 1

    await privacy_service(PrivacyRepository(session)).clear_user_data(owner.id)

    assert await session.get(SharePackage, package.id) is None
    assert await session.get(Ingredient, imported_ingredient.id) is not None
    assert (
        await privacy_service(PrivacyRepository(session)).summary(recipient.id)
    ).imported_packages == 0
