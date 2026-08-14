from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.diary import DiaryEntryType, MealType
from app.exceptions import NotFoundError
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.users import UserRepository
from app.services.diary import DiaryService
from app.services.dishes import DishComponentData, DishService
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientService,
)
from app.services.users import TelegramUserData, UserService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Diary Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


def service(session: AsyncSession) -> DiaryService:
    return DiaryService(
        DiaryRepository(session),
        IngredientRepository(session),
        DishRepository(session),
        NutritionGoalRepository(session),
    )


async def test_ingredient_and_dish_entries_keep_nutrition_snapshots(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9440000001)
    ingredients = IngredientService(IngredientRepository(session))
    chicken = await ingredients.create(
        user_id,
        CreateIngredientData(
            name="Курица",
            kcal_per_100g=Decimal("165"),
            protein_per_100g=Decimal("31"),
            fat_per_100g=Decimal("3.6"),
            carbs_per_100g=Decimal("0"),
        ),
    )
    buckwheat = await ingredients.create(
        user_id,
        CreateIngredientData(
            name="Гречка",
            kcal_per_100g=Decimal("100"),
            protein_per_100g=Decimal("4"),
            fat_per_100g=Decimal("1"),
            carbs_per_100g=Decimal("20"),
        ),
    )
    dish = await DishService(DishRepository(session)).create(
        user_id,
        "Курица с гречкой",
        [
            DishComponentData(chicken.id, Decimal("200")),
            DishComponentData(buckwheat.id, Decimal("150")),
        ],
    )
    diary = service(session)
    entry_date = date(2026, 8, 11)

    ingredient_entry = await diary.add_ingredient(
        user_id=user_id,
        ingredient_id=chicken.id,
        grams=Decimal("200"),
        meal_type=MealType.LUNCH,
        entry_date=entry_date,
    )
    dish_entry = await diary.add_dish(
        user_id=user_id,
        dish_id=dish.dish.id,
        grams=Decimal("175"),
        meal_type=MealType.DINNER,
        entry_date=entry_date,
    )
    summary = await diary.get_day(user_id, entry_date)

    assert ingredient_entry.entry_type is DiaryEntryType.INGREDIENT
    assert dish_entry.entry_type is DiaryEntryType.DISH
    assert ingredient_entry.kcal_snapshot == Decimal("330.00")
    assert dish_entry.kcal_snapshot == Decimal("240.00")
    assert summary.totals.kcal == Decimal("570.00")
    assert summary.totals.protein == Decimal("96.00")

    await ingredients.update_field(
        user_id,
        chicken.id,
        IngredientField.KCAL,
        "160",
    )
    unchanged = await diary.get_day(user_id, entry_date)
    assert unchanged.entries[0].kcal_snapshot == Decimal("330.00")
    assert unchanged.entries[1].kcal_snapshot == Decimal("240.00")

    updated = await diary.update_grams(
        user_id,
        ingredient_entry.id,
        Decimal("100"),
    )
    assert updated.kcal_snapshot == Decimal("160.00")


async def test_diary_entries_are_isolated_by_user(session: AsyncSession) -> None:
    owner_id = await create_user(session, 9440000002)
    other_id = await create_user(session, 9440000003)
    ingredient = await IngredientService(IngredientRepository(session)).create(
        owner_id,
        CreateIngredientData(
            name="Яблоко",
            kcal_per_100g=Decimal("52"),
            protein_per_100g=Decimal("0.3"),
            fat_per_100g=Decimal("0.2"),
            carbs_per_100g=Decimal("14"),
        ),
    )
    diary = service(session)
    entry = await diary.add_ingredient(
        user_id=owner_id,
        ingredient_id=ingredient.id,
        grams=Decimal("150"),
        meal_type=MealType.SNACK,
        entry_date=date(2026, 8, 12),
    )

    with pytest.raises(NotFoundError):
        await diary.get(other_id, entry.id)
    with pytest.raises(NotFoundError):
        await diary.delete(other_id, entry.id)
