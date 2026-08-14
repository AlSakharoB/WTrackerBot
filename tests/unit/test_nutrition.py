from decimal import Decimal

import pytest

from app.exceptions import ValidationError
from app.services.nutrition import (
    DishNutritionValues,
    NutritionComponent,
    NutritionService,
    NutritionValues,
)

CHICKEN_NUTRITION = {
    "kcal_per_100g": Decimal("165"),
    "protein_per_100g": Decimal("31"),
    "fat_per_100g": Decimal("3.6"),
    "carbs_per_100g": Decimal("0"),
}


@pytest.mark.parametrize(
    ("grams", "expected"),
    [
        (
            Decimal("100"),
            NutritionValues(
                kcal=Decimal("165"),
                protein=Decimal("31"),
                fat=Decimal("3.6"),
                carbs=Decimal("0"),
            ),
        ),
        (
            Decimal("200"),
            NutritionValues(
                kcal=Decimal("330"),
                protein=Decimal("62"),
                fat=Decimal("7.2"),
                carbs=Decimal("0"),
            ),
        ),
        (
            Decimal("50"),
            NutritionValues(
                kcal=Decimal("82.5"),
                protein=Decimal("15.5"),
                fat=Decimal("1.8"),
                carbs=Decimal("0"),
            ),
        ),
        (
            Decimal("0"),
            NutritionValues(
                kcal=Decimal("0"),
                protein=Decimal("0"),
                fat=Decimal("0"),
                carbs=Decimal("0"),
            ),
        ),
    ],
)
def test_calculate_ingredient_nutrition_for_standard_weights(
    grams: Decimal,
    expected: NutritionValues,
) -> None:
    result = NutritionService.calculate_ingredient_nutrition(
        **CHICKEN_NUTRITION,
        grams=grams,
    )

    assert result == expected


def test_calculate_ingredient_nutrition_preserves_fractional_precision() -> None:
    result = NutritionService.calculate_ingredient_nutrition(
        kcal_per_100g=Decimal("123.45"),
        protein_per_100g=Decimal("6.78"),
        fat_per_100g=Decimal("1.23"),
        carbs_per_100g=Decimal("20.01"),
        grams=Decimal("37.5"),
    )

    assert result == NutritionValues(
        kcal=Decimal("46.29375"),
        protein=Decimal("2.5425"),
        fat=Decimal("0.46125"),
        carbs=Decimal("7.50375"),
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("grams", Decimal("-1")),
        ("grams", Decimal("NaN")),
        ("grams", Decimal("Infinity")),
        ("kcal_per_100g", Decimal("-1")),
        ("protein_per_100g", Decimal("NaN")),
        ("fat_per_100g", Decimal("Infinity")),
        ("carbs_per_100g", Decimal("-0.01")),
    ],
)
def test_calculate_ingredient_nutrition_rejects_invalid_values(
    field_name: str,
    invalid_value: Decimal,
) -> None:
    values = CHICKEN_NUTRITION | {
        "grams": Decimal("100"),
        field_name: invalid_value,
    }

    with pytest.raises(ValidationError):
        NutritionService.calculate_ingredient_nutrition(**values)


def test_calculate_ingredient_nutrition_rejects_float() -> None:
    values = CHICKEN_NUTRITION | {"grams": 100.0}

    with pytest.raises(TypeError, match="grams must be Decimal"):
        NutritionService.calculate_ingredient_nutrition(**values)  # type: ignore[arg-type]


def test_calculate_dish_nutrition_sums_components_and_calculates_per_100g() -> None:
    result = NutritionService.calculate_dish_nutrition(
        [
            NutritionComponent(
                nutrition_per_100g=NutritionValues(
                    kcal=Decimal("100"),
                    protein=Decimal("10"),
                    fat=Decimal("5"),
                    carbs=Decimal("20"),
                ),
                grams=Decimal("200"),
            ),
            NutritionComponent(
                nutrition_per_100g=NutritionValues(
                    kcal=Decimal("300"),
                    protein=Decimal("20"),
                    fat=Decimal("10"),
                    carbs=Decimal("30"),
                ),
                grams=Decimal("100"),
            ),
        ]
    )

    assert result == DishNutritionValues(
        total_weight=Decimal("300"),
        total=NutritionValues(
            kcal=Decimal("500"),
            protein=Decimal("40"),
            fat=Decimal("20"),
            carbs=Decimal("70"),
        ),
        per_100g=NutritionValues(
            kcal=Decimal("166.6666666666666666666666666"),
            protein=Decimal("13.33333333333333333333333333"),
            fat=Decimal("6.666666666666666666666666666"),
            carbs=Decimal("23.33333333333333333333333333"),
        ),
    )


def test_calculate_dish_nutrition_rejects_empty_recipe() -> None:
    with pytest.raises(ValidationError):
        NutritionService.calculate_dish_nutrition([])
