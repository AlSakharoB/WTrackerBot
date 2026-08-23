from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from math import ceil
from re import fullmatch

from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.ingredients import IngredientRepository
from app.search import (
    DUPLICATE_NAME_SIMILARITY_THRESHOLD,
    names_have_different_numbers,
    normalize_search_text,
)

INGREDIENTS_PAGE_SIZE = 8
NUTRITION_LIMITS = {
    "kcal_per_100g": Decimal("1500"),
    "protein_per_100g": Decimal("100"),
    "fat_per_100g": Decimal("100"),
    "carbs_per_100g": Decimal("100"),
}


class IngredientField(StrEnum):
    NAME = "name"
    KCAL = "kcal_per_100g"
    PROTEIN = "protein_per_100g"
    FAT = "fat_per_100g"
    CARBS = "carbs_per_100g"


@dataclass(frozen=True, slots=True)
class CreateIngredientData:
    name: str
    kcal_per_100g: Decimal
    protein_per_100g: Decimal
    fat_per_100g: Decimal
    carbs_per_100g: Decimal


@dataclass(frozen=True, slots=True)
class IngredientPage:
    items: list[Ingredient]
    page: int
    pages: int
    total: int


def normalize_ingredient_name(value: str) -> tuple[str, str]:
    name = " ".join(value.split())
    name_normalized = normalize_search_text(name)
    if not name or not name_normalized or len(name) > 255 or len(name_normalized) > 255:
        raise ValidationError("Введите название от 1 до 255 символов.")
    return name, name_normalized


def parse_nutrition_value(field: IngredientField, raw_value: str) -> Decimal:
    if field is IngredientField.NAME:
        raise ValueError("Name is not a nutrition field")

    normalized_value = raw_value.strip().replace(",", ".")
    if fullmatch(r"\d+(?:\.\d+)?", normalized_value) is None:
        raise ValidationError(_nutrition_error_message(field))

    try:
        value = Decimal(normalized_value)
    except InvalidOperation as error:
        raise ValidationError(_nutrition_error_message(field)) from error

    limit = NUTRITION_LIMITS[field.value]
    if not value.is_finite() or value < 0 or value > limit:
        raise ValidationError(_nutrition_error_message(field))
    return value


def _nutrition_error_message(field: IngredientField) -> str:
    limit = NUTRITION_LIMITS[field.value]
    return f"Введите число от 0 до {limit}.\nНапример: 150 или 150.5"


class IngredientService:
    def __init__(self, repository: IngredientRepository) -> None:
        self._repository = repository

    async def create(
        self,
        user_id: int,
        data: CreateIngredientData,
    ) -> Ingredient:
        name, name_normalized = normalize_ingredient_name(data.name)
        validated = {
            field.value: parse_nutrition_value(field, str(getattr(data, field.value)))
            for field in IngredientField
            if field is not IngredientField.NAME
        }
        await self._raise_if_similar_name_exists(user_id, name_normalized)
        return await self._repository.create(
            user_id=user_id,
            name=name,
            name_normalized=name_normalized,
            **validated,
        )

    async def create_import_copy(
        self,
        user_id: int,
        data: CreateIngredientData,
    ) -> Ingredient:
        """Create an explicitly approved import copy without fuzzy rejection."""
        name, name_normalized = normalize_ingredient_name(data.name)
        validated = {
            field.value: parse_nutrition_value(field, str(getattr(data, field.value)))
            for field in IngredientField
            if field is not IngredientField.NAME
        }
        return await self._repository.create(
            user_id=user_id,
            name=name,
            name_normalized=name_normalized,
            **validated,
        )

    async def check_name_available(self, user_id: int, name: str) -> None:
        _, name_normalized = normalize_ingredient_name(name)
        await self._raise_if_similar_name_exists(user_id, name_normalized)

    async def get(self, user_id: int, ingredient_id: int) -> Ingredient:
        ingredient = await self._repository.get_by_id(ingredient_id, user_id)
        if ingredient is None:
            raise NotFoundError("Ингредиент не найден.")
        return ingredient

    async def list_page(self, user_id: int, page: int) -> IngredientPage:
        total = await self._repository.count(user_id)
        pages = max(1, ceil(total / INGREDIENTS_PAGE_SIZE))
        current_page = min(max(page, 1), pages)
        items = await self._repository.list(
            user_id,
            limit=INGREDIENTS_PAGE_SIZE,
            offset=(current_page - 1) * INGREDIENTS_PAGE_SIZE,
        )
        return IngredientPage(
            items=items,
            page=current_page,
            pages=pages,
            total=total,
        )

    async def update_field(
        self,
        user_id: int,
        ingredient_id: int,
        field: IngredientField,
        raw_value: str,
    ) -> Ingredient:
        ingredient = await self.get(user_id, ingredient_id)
        values: dict[str, str | Decimal]
        if field is IngredientField.NAME:
            name, name_normalized = normalize_ingredient_name(raw_value)
            duplicate = await self._repository.get_by_normalized_name(
                user_id,
                name_normalized,
            )
            if duplicate is not None and duplicate.id != ingredient.id:
                raise DuplicateError("Ингредиент с таким названием уже существует.")
            values = {"name": name, "name_normalized": name_normalized}
        else:
            values = {field.value: parse_nutrition_value(field, raw_value)}

        updated = await self._repository.update(
            ingredient_id,
            user_id,
            values,
        )
        if updated is None:
            raise NotFoundError("Ингредиент не найден.")
        return updated

    async def delete(self, user_id: int, ingredient_id: int) -> None:
        ingredient = await self.get(user_id, ingredient_id)
        dish_names = await self._repository.get_usage_dish_names(
            ingredient.id,
            user_id,
        )
        if dish_names:
            formatted_names = "\n".join(f"• {name}" for name in dish_names)
            raise ValidationError(
                "Этот ингредиент используется в блюдах:\n\n"
                f"{formatted_names}\n\n"
                "Сначала удалите ингредиент из этих блюд."
            )
        deleted = await self._repository.delete(ingredient_id, user_id)
        if not deleted:
            raise NotFoundError("Ингредиент не найден.")

    async def _raise_if_similar_name_exists(
        self,
        user_id: int,
        name_normalized: str,
    ) -> None:
        candidates = await self._repository.find_similar_names(
            user_id,
            name_normalized,
            DUPLICATE_NAME_SIMILARITY_THRESHOLD,
        )
        duplicate = next(
            (
                candidate
                for candidate in candidates
                if not names_have_different_numbers(
                    name_normalized,
                    candidate.name_normalized,
                )
            ),
            None,
        )
        if duplicate is not None:
            raise DuplicateError(
                f"Похожий ингредиент «{duplicate.name}» уже существует."
            )
