from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil
from re import fullmatch

from app.db.models.dish import Dish
from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.repositories.dishes import DishRecord, DishRepository
from app.search import (
    DUPLICATE_NAME_SIMILARITY_THRESHOLD,
    names_have_different_numbers,
    normalize_search_text,
)
from app.services.nutrition import (
    DishNutritionValues,
    NutritionComponent,
    NutritionService,
    NutritionValues,
)

DISHES_PAGE_SIZE = 8
MAX_COMPONENT_GRAMS = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class DishComponentData:
    ingredient_id: int
    grams: Decimal


@dataclass(frozen=True, slots=True)
class DishComponent:
    ingredient: Ingredient
    grams: Decimal


@dataclass(frozen=True, slots=True)
class DishDetails:
    dish: Dish
    components: list[DishComponent]
    nutrition: DishNutritionValues


@dataclass(frozen=True, slots=True)
class DishPreview:
    name: str
    components: list[DishComponent]
    nutrition: DishNutritionValues


@dataclass(frozen=True, slots=True)
class DishPage:
    items: list[Dish]
    page: int
    pages: int
    total: int


def normalize_dish_name(value: str) -> tuple[str, str]:
    name = " ".join(value.split())
    name_normalized = normalize_search_text(name)
    if not name or not name_normalized or len(name) > 255 or len(name_normalized) > 255:
        raise ValidationError("Введите название блюда от 1 до 255 символов.")
    return name, name_normalized


def parse_component_grams(raw_value: str) -> Decimal:
    normalized = raw_value.strip().replace(",", ".")
    if fullmatch(r"\d+(?:\.\d+)?", normalized) is None:
        raise ValidationError("Введите количество граммов больше 0.")
    try:
        grams = Decimal(normalized)
    except InvalidOperation as error:
        raise ValidationError("Введите количество граммов больше 0.") from error
    if not grams.is_finite() or grams <= 0 or grams > MAX_COMPONENT_GRAMS:
        raise ValidationError("Введите количество граммов больше 0.")
    return grams


class DishService:
    def __init__(self, repository: DishRepository) -> None:
        self._repository = repository

    async def create(
        self,
        user_id: int,
        name: str,
        components: list[DishComponentData],
    ) -> DishDetails:
        normalized_name, name_key = normalize_dish_name(name)
        validated = await self._validate_components(user_id, components)
        await self._raise_if_similar_name_exists(user_id, name_key)
        dish = await self._repository.create(
            user_id=user_id,
            name=normalized_name,
            name_normalized=name_key,
            components=[(item.ingredient_id, item.grams) for item in components],
        )
        return self._build_details(dish, validated)

    async def check_name_available(self, user_id: int, name: str) -> None:
        _, name_normalized = normalize_dish_name(name)
        await self._raise_if_similar_name_exists(user_id, name_normalized)

    async def replace(
        self,
        user_id: int,
        dish_id: int,
        name: str,
        components: list[DishComponentData],
    ) -> DishDetails:
        normalized_name, name_key = normalize_dish_name(name)
        validated = await self._validate_components(user_id, components)
        dish = await self._repository.replace(
            dish_id=dish_id,
            user_id=user_id,
            name=normalized_name,
            name_normalized=name_key,
            components=[(item.ingredient_id, item.grams) for item in components],
        )
        if dish is None:
            raise NotFoundError("Блюдо не найдено.")
        return self._build_details(dish, validated)

    async def preview(
        self,
        user_id: int,
        name: str,
        components: list[DishComponentData],
    ) -> DishPreview:
        normalized_name, _ = normalize_dish_name(name)
        validated = await self._validate_components(user_id, components)
        return DishPreview(
            name=normalized_name,
            components=validated,
            nutrition=self._calculate_nutrition(validated),
        )

    async def get(self, user_id: int, dish_id: int) -> DishDetails:
        record = await self._repository.get_by_id(dish_id, user_id)
        if record is None:
            raise NotFoundError("Блюдо не найдено.")
        return self._details_from_record(record)

    async def list_page(self, user_id: int, page: int) -> DishPage:
        total = await self._repository.count(user_id)
        pages = max(1, ceil(total / DISHES_PAGE_SIZE))
        current_page = min(max(page, 1), pages)
        items = await self._repository.list(
            user_id,
            limit=DISHES_PAGE_SIZE,
            offset=(current_page - 1) * DISHES_PAGE_SIZE,
        )
        return DishPage(items=items, page=current_page, pages=pages, total=total)

    async def delete(self, user_id: int, dish_id: int) -> None:
        if not await self._repository.delete(dish_id, user_id):
            raise NotFoundError("Блюдо не найдено.")

    async def _validate_components(
        self,
        user_id: int,
        components: list[DishComponentData],
    ) -> list[DishComponent]:
        if not components:
            raise ValidationError("Добавьте хотя бы один ингредиент.")
        ingredient_ids = [item.ingredient_id for item in components]
        if len(ingredient_ids) != len(set(ingredient_ids)):
            raise DuplicateError("Ингредиент уже добавлен в блюдо.")
        for item in components:
            parse_component_grams(str(item.grams))

        ingredients = await self._repository.get_ingredients(
            user_id,
            set(ingredient_ids),
        )
        by_id = {ingredient.id: ingredient for ingredient in ingredients}
        if len(by_id) != len(ingredient_ids):
            raise NotFoundError("Один из ингредиентов не найден.")
        return [
            DishComponent(ingredient=by_id[item.ingredient_id], grams=item.grams)
            for item in components
        ]

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
            raise DuplicateError(f"Похожее блюдо «{duplicate.name}» уже существует.")

    @staticmethod
    def _details_from_record(record: DishRecord) -> DishDetails:
        components = [
            DishComponent(ingredient=item.ingredient, grams=item.grams)
            for item in record.components
        ]
        return DishService._build_details(record.dish, components)

    @staticmethod
    def _build_details(dish: Dish, components: list[DishComponent]) -> DishDetails:
        return DishDetails(
            dish=dish,
            components=components,
            nutrition=DishService._calculate_nutrition(components),
        )

    @staticmethod
    def _calculate_nutrition(
        components: list[DishComponent],
    ) -> DishNutritionValues:
        return NutritionService.calculate_dish_nutrition(
            NutritionComponent(
                nutrition_per_100g=NutritionValues(
                    kcal=component.ingredient.kcal_per_100g,
                    protein=component.ingredient.protein_per_100g,
                    fat=component.ingredient.fat_per_100g,
                    carbs=component.ingredient.carbs_per_100g,
                ),
                grams=component.grams,
            )
            for component in components
        )
