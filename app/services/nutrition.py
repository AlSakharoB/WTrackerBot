from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.exceptions import ValidationError

ONE_HUNDRED_GRAMS = Decimal("100")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class NutritionValues:
    kcal: Decimal
    protein: Decimal
    fat: Decimal
    carbs: Decimal


@dataclass(frozen=True, slots=True)
class NutritionComponent:
    nutrition_per_100g: NutritionValues
    grams: Decimal


@dataclass(frozen=True, slots=True)
class DishNutritionValues:
    total_weight: Decimal
    total: NutritionValues
    per_100g: NutritionValues


@dataclass(frozen=True, slots=True)
class MacroPercentages:
    protein: Decimal
    fat: Decimal
    carbs: Decimal


class NutritionService:
    @staticmethod
    def calculate_ingredient_nutrition(
        *,
        kcal_per_100g: Decimal,
        protein_per_100g: Decimal,
        fat_per_100g: Decimal,
        carbs_per_100g: Decimal,
        grams: Decimal,
    ) -> NutritionValues:
        values = {
            "kcal_per_100g": kcal_per_100g,
            "protein_per_100g": protein_per_100g,
            "fat_per_100g": fat_per_100g,
            "carbs_per_100g": carbs_per_100g,
            "grams": grams,
        }
        for field_name, value in values.items():
            NutritionService._validate_decimal(field_name, value)

        if grams == ZERO:
            return NutritionValues(
                kcal=ZERO,
                protein=ZERO,
                fat=ZERO,
                carbs=ZERO,
            )

        factor = grams / ONE_HUNDRED_GRAMS
        return NutritionValues(
            kcal=kcal_per_100g * factor,
            protein=protein_per_100g * factor,
            fat=fat_per_100g * factor,
            carbs=carbs_per_100g * factor,
        )

    @staticmethod
    def calculate_dish_nutrition(
        components: Iterable[NutritionComponent],
    ) -> DishNutritionValues:
        total_weight = ZERO
        total_kcal = ZERO
        total_protein = ZERO
        total_fat = ZERO
        total_carbs = ZERO

        for component in components:
            calculated = NutritionService.calculate_ingredient_nutrition(
                kcal_per_100g=component.nutrition_per_100g.kcal,
                protein_per_100g=component.nutrition_per_100g.protein,
                fat_per_100g=component.nutrition_per_100g.fat,
                carbs_per_100g=component.nutrition_per_100g.carbs,
                grams=component.grams,
            )
            total_weight += component.grams
            total_kcal += calculated.kcal
            total_protein += calculated.protein
            total_fat += calculated.fat
            total_carbs += calculated.carbs

        if total_weight <= ZERO:
            raise ValidationError("Dish must contain a positive ingredient weight")

        total = NutritionValues(
            kcal=total_kcal,
            protein=total_protein,
            fat=total_fat,
            carbs=total_carbs,
        )
        per_100g_factor = ONE_HUNDRED_GRAMS / total_weight
        return DishNutritionValues(
            total_weight=total_weight,
            total=total,
            per_100g=NutritionValues(
                kcal=total.kcal * per_100g_factor,
                protein=total.protein * per_100g_factor,
                fat=total.fat * per_100g_factor,
                carbs=total.carbs * per_100g_factor,
            ),
        )

    @staticmethod
    def sum_nutrition(values: Iterable[NutritionValues]) -> NutritionValues:
        total = NutritionValues(kcal=ZERO, protein=ZERO, fat=ZERO, carbs=ZERO)
        for value in values:
            for field_name in ("kcal", "protein", "fat", "carbs"):
                NutritionService._validate_decimal(
                    field_name,
                    getattr(value, field_name),
                )
            total = NutritionValues(
                kcal=total.kcal + value.kcal,
                protein=total.protein + value.protein,
                fat=total.fat + value.fat,
                carbs=total.carbs + value.carbs,
            )
        return total

    @staticmethod
    def calculate_macro_percentages(
        *,
        protein: Decimal,
        fat: Decimal,
        carbs: Decimal,
    ) -> MacroPercentages:
        for field_name, value in {
            "protein": protein,
            "fat": fat,
            "carbs": carbs,
        }.items():
            NutritionService._validate_decimal(field_name, value)

        protein_energy = protein * Decimal("4")
        fat_energy = fat * Decimal("9")
        carbs_energy = carbs * Decimal("4")
        total_energy = protein_energy + fat_energy + carbs_energy
        if total_energy == ZERO:
            return MacroPercentages(protein=ZERO, fat=ZERO, carbs=ZERO)

        return MacroPercentages(
            protein=protein_energy / total_energy * Decimal("100"),
            fat=fat_energy / total_energy * Decimal("100"),
            carbs=carbs_energy / total_energy * Decimal("100"),
        )

    @staticmethod
    def _validate_decimal(field_name: str, value: Decimal) -> None:
        if not isinstance(value, Decimal):
            raise TypeError(f"{field_name} must be Decimal")
        if not value.is_finite() or value < ZERO:
            raise ValidationError(f"{field_name} must be a finite non-negative value")
