from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.users import UserRepository
from app.services.diary import DiaryService
from app.services.nutrition_goals import NutritionGoalData, NutritionGoalService
from app.services.users import TelegramUserData, UserService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Nutrition Goal Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


def goal_data(
    kcal: str | None,
    protein: str | None = None,
    fat: str | None = None,
    carbs: str | None = None,
) -> NutritionGoalData:
    return NutritionGoalData(
        kcal_target=Decimal(kcal) if kcal is not None else None,
        protein_target_g=Decimal(protein) if protein is not None else None,
        fat_target_g=Decimal(fat) if fat is not None else None,
        carbs_target_g=Decimal(carbs) if carbs is not None else None,
    )


async def test_goal_change_preserves_historical_periods(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9880000001)
    service = NutritionGoalService(NutritionGoalRepository(session))
    first = await service.set_goal(
        user_id,
        goal_data("2000", "140"),
        date(2026, 8, 1),
    )
    second = await service.set_goal(
        user_id,
        goal_data("2200", "160", "70", "220"),
        date(2026, 8, 10),
    )

    old_day = await service.get_for_date(user_id, date(2026, 8, 9))
    new_day = await service.get_for_date(user_id, date(2026, 8, 10))
    diary = DiaryService(
        DiaryRepository(session),
        IngredientRepository(session),
        DishRepository(session),
        NutritionGoalRepository(session),
    )
    old_summary = await diary.get_day(user_id, date(2026, 8, 9))
    new_summary = await diary.get_day(user_id, date(2026, 8, 10))

    assert old_day is not None
    assert old_day.id == first.id
    assert old_day.kcal_target == Decimal("2000")
    assert old_day.effective_to == date(2026, 8, 9)
    assert new_day is not None
    assert new_day.id == second.id
    assert new_day.kcal_target == Decimal("2200")
    assert old_summary.nutrition_goal is not None
    assert old_summary.nutrition_goal.id == first.id
    assert new_summary.nutrition_goal is not None
    assert new_summary.nutrition_goal.id == second.id


async def test_same_start_date_replaces_period_without_duplicate(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9880000002)
    service = NutritionGoalService(NutritionGoalRepository(session))
    original = await service.set_goal(
        user_id,
        goal_data("2000"),
        date(2026, 8, 14),
    )
    replaced = await service.set_goal(
        user_id,
        goal_data(None, "150"),
        date(2026, 8, 14),
    )

    assert replaced.id == original.id
    assert replaced.kcal_target is None
    assert replaced.protein_target_g == Decimal("150")


async def test_goal_history_is_isolated_and_disable_preserves_old_days(
    session: AsyncSession,
) -> None:
    first_user = await create_user(session, 9880000003)
    second_user = await create_user(session, 9880000004)
    service = NutritionGoalService(NutritionGoalRepository(session))
    first_goal = await service.set_goal(
        first_user,
        goal_data("1800"),
        date(2026, 8, 1),
    )
    await service.set_goal(
        second_user,
        goal_data("2500"),
        date(2026, 8, 1),
    )

    await service.disable(first_user, first_goal.id, date(2026, 8, 15))

    first_old = await service.get_for_date(first_user, date(2026, 8, 14))
    first_disabled = await service.get_for_date(first_user, date(2026, 8, 15))
    second_active = await service.get_for_date(second_user, date(2026, 8, 15))
    assert first_old is not None
    assert first_old.kcal_target == Decimal("1800")
    assert first_disabled is None
    assert second_active is not None
    assert second_active.kcal_target == Decimal("2500")
