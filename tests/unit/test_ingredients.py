from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.bot.handlers.ingredients import ingredient_card
from app.bot.keyboards.ingredients import (
    IngredientCallback,
    build_ingredient_detail_keyboard,
)
from app.db.models.ingredient import Ingredient
from app.exceptions import NotFoundError, ValidationError
from app.services.ingredients import (
    INGREDIENTS_PAGE_SIZE,
    CreateIngredientData,
    IngredientField,
    IngredientService,
    normalize_ingredient_name,
    parse_nutrition_value,
)
from app.utils.decimal import format_decimal


def test_normalize_ingredient_name_collapses_spaces_and_lowercases() -> None:
    assert normalize_ingredient_name("  Куриная   грудка ") == (
        "Куриная грудка",
        "куриная грудка",
    )


@pytest.mark.parametrize("value", ["", "   ", "x" * 256])
def test_normalize_ingredient_name_rejects_invalid_length(value: str) -> None:
    with pytest.raises(ValidationError):
        normalize_ingredient_name(value)


@pytest.mark.parametrize(
    ("field", "raw_value", "expected"),
    [
        (IngredientField.KCAL, "0", Decimal("0")),
        (IngredientField.KCAL, "1500", Decimal("1500")),
        (IngredientField.PROTEIN, "10.5", Decimal("10.5")),
        (IngredientField.FAT, "10,5", Decimal("10.5")),
        (IngredientField.CARBS, " 100 ", Decimal("100")),
    ],
)
def test_parse_nutrition_value_accepts_supported_numbers(
    field: IngredientField,
    raw_value: str,
    expected: Decimal,
) -> None:
    assert parse_nutrition_value(field, raw_value) == expected


@pytest.mark.parametrize(
    ("field", "raw_value"),
    [
        (IngredientField.KCAL, "-1"),
        (IngredientField.KCAL, "1500.01"),
        (IngredientField.PROTEIN, "100.01"),
        (IngredientField.FAT, "abc"),
        (IngredientField.FAT, "1e2"),
        (IngredientField.FAT, ".5"),
        (IngredientField.FAT, "10."),
        (IngredientField.CARBS, "NaN"),
        (IngredientField.CARBS, "Infinity"),
    ],
)
def test_parse_nutrition_value_rejects_invalid_numbers(
    field: IngredientField,
    raw_value: str,
) -> None:
    with pytest.raises(ValidationError):
        parse_nutrition_value(field, raw_value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("31.0000"), "31"),
        (Decimal("3.6000"), "3.6"),
        (Decimal("82.456"), "82.46"),
    ],
)
def test_format_decimal(value: Decimal, expected: str) -> None:
    assert format_decimal(value) == expected


async def test_service_create_validates_and_normalizes_data() -> None:
    ingredient = Ingredient(id=1, user_id=10, name="Куриная грудка")
    repository = Mock()
    repository.create = AsyncMock(return_value=ingredient)
    service = IngredientService(repository)

    result = await service.create(
        10,
        CreateIngredientData(
            name="  Куриная   грудка ",
            kcal_per_100g=Decimal("165"),
            protein_per_100g=Decimal("31"),
            fat_per_100g=Decimal("3.6"),
            carbs_per_100g=Decimal("0"),
        ),
    )

    assert result is ingredient
    repository.create.assert_awaited_once_with(
        user_id=10,
        name="Куриная грудка",
        name_normalized="куриная грудка",
        kcal_per_100g=Decimal("165"),
        protein_per_100g=Decimal("31"),
        fat_per_100g=Decimal("3.6"),
        carbs_per_100g=Decimal("0"),
    )


async def test_service_clamps_page_to_available_range() -> None:
    repository = Mock()
    repository.count = AsyncMock(return_value=9)
    repository.list = AsyncMock(return_value=[])
    service = IngredientService(repository)

    page = await service.list_page(10, 99)

    assert page.page == 2
    assert page.pages == 2
    repository.list.assert_awaited_once_with(
        10,
        limit=INGREDIENTS_PAGE_SIZE,
        offset=INGREDIENTS_PAGE_SIZE,
    )


async def test_service_rejects_foreign_or_missing_ingredient() -> None:
    repository = Mock()
    repository.get_by_id = AsyncMock(return_value=None)
    service = IngredientService(repository)

    with pytest.raises(NotFoundError):
        await service.get(user_id=10, ingredient_id=999)

    repository.get_by_id.assert_awaited_once_with(999, 10)


def test_ingredient_card_escapes_name_and_formats_values() -> None:
    ingredient = Ingredient(
        id=1,
        user_id=10,
        name="<Курица>",
        name_normalized="<курица>",
        kcal_per_100g=Decimal("165.00"),
        protein_per_100g=Decimal("31.00"),
        fat_per_100g=Decimal("3.60"),
        carbs_per_100g=Decimal("0.00"),
    )

    card = ingredient_card(ingredient)

    assert "&lt;Курица&gt;" in card
    assert "165 ккал" in card
    assert "Б: 31 г" in card
    assert "Ж: 3.6 г" in card


def test_ingredient_callbacks_fit_telegram_limit() -> None:
    callback_data = IngredientCallback(
        action="delete_confirm",
        ingredient_id=9_223_372_036_854_775_807,
        page=999_999,
    ).pack()

    assert len(callback_data.encode()) <= 64
    keyboard = build_ingredient_detail_keyboard(ingredient_id=1, page=1)
    assert len(keyboard.inline_keyboard) == 3
