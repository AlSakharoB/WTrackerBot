from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.repositories.users import UserRepository
from app.services.dishes import DishComponentData, DishService
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientService,
)
from app.services.search import SearchService
from app.services.users import TelegramUserData, UserService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Dish Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


async def create_ingredient(
    session: AsyncSession,
    user_id: int,
    name: str,
    kcal: str,
    protein: str,
    fat: str,
    carbs: str,
) -> int:
    ingredient = await IngredientService(IngredientRepository(session)).create(
        user_id,
        CreateIngredientData(
            name=name,
            kcal_per_100g=Decimal(kcal),
            protein_per_100g=Decimal(protein),
            fat_per_100g=Decimal(fat),
            carbs_per_100g=Decimal(carbs),
        ),
    )
    return ingredient.id


async def test_dish_crud_and_dynamic_nutrition(session: AsyncSession) -> None:
    user_id = await create_user(session, 9330000001)
    chicken_id = await create_ingredient(
        session, user_id, "Курица", "165", "31", "3.6", "0"
    )
    buckwheat_id = await create_ingredient(
        session, user_id, "Гречка", "100", "4", "1", "20"
    )
    service = DishService(DishRepository(session))

    details = await service.create(
        user_id,
        "  Курица   с гречкой ",
        [
            DishComponentData(chicken_id, Decimal("200")),
            DishComponentData(buckwheat_id, Decimal("150")),
        ],
    )

    assert details.dish.name == "Курица с гречкой"
    assert details.nutrition.total_weight == Decimal("350")
    assert details.nutrition.total.kcal == Decimal("480.00")
    assert details.nutrition.total.protein == Decimal("68.00")

    await IngredientService(IngredientRepository(session)).update_field(
        user_id,
        chicken_id,
        IngredientField.KCAL,
        "160",
    )
    recalculated = await service.get(user_id, details.dish.id)
    assert recalculated.nutrition.total.kcal == Decimal("470.00")

    replaced = await service.replace(
        user_id,
        details.dish.id,
        "Курица",
        [DishComponentData(chicken_id, Decimal("100"))],
    )
    assert replaced.dish.name == "Курица"
    assert len(replaced.components) == 1
    assert replaced.nutrition.total.kcal == Decimal("160.00")

    found = await SearchService(SearchRepository(session)).search_dishes(
        user_id,
        "кур",
    )
    assert found[0].entity_id == details.dish.id
    await service.delete(user_id, details.dish.id)
    with pytest.raises(NotFoundError):
        await service.get(user_id, details.dish.id)


async def test_dish_names_are_unique_per_user(session: AsyncSession) -> None:
    first_user = await create_user(session, 9330000002)
    second_user = await create_user(session, 9330000003)
    first_ingredient = await create_ingredient(
        session, first_user, "Яйцо", "150", "12", "10", "1"
    )
    second_ingredient = await create_ingredient(
        session, second_user, "Яйцо", "150", "12", "10", "1"
    )
    service = DishService(DishRepository(session))

    await service.create(
        first_user,
        "Омлет",
        [DishComponentData(first_ingredient, Decimal("100"))],
    )
    await service.create(
        second_user,
        " омлет ",
        [DishComponentData(second_ingredient, Decimal("100"))],
    )
    with pytest.raises(DuplicateError):
        await service.create(
            first_user,
            "ОМЛЕТ",
            [DishComponentData(first_ingredient, Decimal("200"))],
        )


async def test_dish_and_components_are_isolated_by_user(
    session: AsyncSession,
) -> None:
    owner = await create_user(session, 9330000004)
    other = await create_user(session, 9330000005)
    owner_ingredient = await create_ingredient(
        session, owner, "Творог", "120", "18", "5", "3"
    )
    dish = await DishService(DishRepository(session)).create(
        owner,
        "Творог",
        [DishComponentData(owner_ingredient, Decimal("200"))],
    )
    service = DishService(DishRepository(session))

    with pytest.raises(NotFoundError):
        await service.get(other, dish.dish.id)
    with pytest.raises(NotFoundError):
        await service.delete(other, dish.dish.id)
    with pytest.raises(NotFoundError):
        await service.create(
            other,
            "Чужой творог",
            [DishComponentData(owner_ingredient, Decimal("100"))],
        )


async def test_used_ingredient_cannot_be_deleted(session: AsyncSession) -> None:
    user_id = await create_user(session, 9330000006)
    ingredient_id = await create_ingredient(
        session, user_id, "Авокадо", "160", "2", "15", "9"
    )
    await DishService(DishRepository(session)).create(
        user_id,
        "Салат",
        [DishComponentData(ingredient_id, Decimal("100"))],
    )

    with pytest.raises(ValidationError, match="Салат"):
        await IngredientService(IngredientRepository(session)).delete(
            user_id,
            ingredient_id,
        )
