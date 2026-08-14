from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.keyboards.dishes import (
    DishCallback,
    DishIngredientCallback,
    DishIngredientPageCallback,
)
from app.db.models.dish import Dish
from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.services.dishes import (
    DishComponentData,
    DishService,
    normalize_dish_name,
    parse_component_grams,
)


def make_ingredient(ingredient_id: int, name: str) -> Ingredient:
    return Ingredient(
        id=ingredient_id,
        user_id=10,
        name=name,
        name_normalized=name.lower(),
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("20"),
    )


def test_normalize_dish_name() -> None:
    assert normalize_dish_name("  Курица   с гречкой ") == (
        "Курица с гречкой",
        "курица с гречкой",
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", Decimal("1")),
        ("150.5", Decimal("150.5")),
        ("150,5", Decimal("150.5")),
    ],
)
def test_parse_component_grams(raw_value: str, expected: Decimal) -> None:
    assert parse_component_grams(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["0", "-1", "abc", "NaN", "1000000.01"])
def test_parse_component_grams_rejects_invalid_value(raw_value: str) -> None:
    with pytest.raises(ValidationError):
        parse_component_grams(raw_value)


async def test_create_validates_ingredients_and_returns_dynamic_nutrition() -> None:
    ingredient = make_ingredient(1, "Гречка")
    dish = Dish(id=5, user_id=10, name="Гречка", name_normalized="гречка")
    repository = Mock()
    repository.get_ingredients = AsyncMock(return_value=[ingredient])
    repository.create = AsyncMock(return_value=dish)
    service = DishService(repository)

    details = await service.create(
        10,
        " Гречка ",
        [DishComponentData(ingredient_id=1, grams=Decimal("250"))],
    )

    assert details.nutrition.total_weight == Decimal("250")
    assert details.nutrition.total.kcal == Decimal("250.0")
    repository.create.assert_awaited_once_with(
        user_id=10,
        name="Гречка",
        name_normalized="гречка",
        components=[(1, Decimal("250"))],
    )


async def test_create_rejects_empty_and_duplicate_components() -> None:
    repository = Mock()
    service = DishService(repository)

    with pytest.raises(ValidationError):
        await service.create(10, "Пустое", [])
    with pytest.raises(DuplicateError):
        await service.create(
            10,
            "Дубли",
            [
                DishComponentData(1, Decimal("100")),
                DishComponentData(1, Decimal("200")),
            ],
        )


async def test_create_rejects_foreign_ingredient() -> None:
    repository = Mock()
    repository.get_ingredients = AsyncMock(return_value=[])
    service = DishService(repository)

    with pytest.raises(NotFoundError):
        await service.create(
            10,
            "Чужой продукт",
            [DishComponentData(999, Decimal("100"))],
        )


def test_dish_callbacks_fit_telegram_limit() -> None:
    callbacks = [
        DishCallback(
            action="delete_confirm",
            dish_id=9_223_372_036_854_775_807,
            page=999_999,
        ).pack(),
        DishIngredientCallback(
            action="select",
            ingredient_id=9_223_372_036_854_775_807,
        ).pack(),
        DishIngredientPageCallback(page=999_999).pack(),
    ]

    assert all(len(callback.encode()) <= 64 for callback in callbacks)
