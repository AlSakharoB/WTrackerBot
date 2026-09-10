from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import ceil
from re import fullmatch

from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.nutrition_goal import NutritionGoal
from app.exceptions import NotFoundError, StaleDataError, ValidationError
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRecord, DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.services.nutrition import (
    MacroPercentages,
    NutritionComponent,
    NutritionService,
    NutritionValues,
)

MAX_ENTRY_GRAMS = Decimal("1000000")
MIN_ENTRY_GRAMS = Decimal("0.01")
DIARY_ENTRIES_PAGE_SIZE = 8


@dataclass(frozen=True, slots=True)
class DaySummary:
    entry_date: date
    entries: list[DiaryEntry]
    totals: NutritionValues
    macro_percentages: MacroPercentages
    nutrition_goal: NutritionGoal | None


@dataclass(frozen=True, slots=True)
class DiaryPreview:
    source_name: str
    grams: Decimal
    nutrition: NutritionValues


@dataclass(frozen=True, slots=True)
class DiaryEntryPage:
    items: list[DiaryEntry]
    page: int
    pages: int
    total: int


def parse_entry_grams(raw_value: str) -> Decimal:
    normalized = raw_value.strip().replace(",", ".")
    if fullmatch(r"\d+(?:\.\d+)?", normalized) is None:
        raise ValidationError("Введите количество граммов больше 0.")
    try:
        grams = Decimal(normalized)
    except InvalidOperation as error:
        raise ValidationError("Введите количество граммов больше 0.") from error
    if not grams.is_finite() or grams < MIN_ENTRY_GRAMS or grams > MAX_ENTRY_GRAMS:
        raise ValidationError("Введите количество граммов больше 0.")
    return grams


def parse_entry_date(raw_value: str) -> date:
    value = raw_value.strip()
    try:
        if fullmatch(r"\d{2}\.\d{2}\.\d{4}", value):
            return datetime.strptime(value, "%d.%m.%Y").date()
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValidationError(
            "Введите дату в формате ДД.ММ.ГГГГ.\nНапример: 11.08.2026"
        ) from error


class DiaryService:
    def __init__(
        self,
        repository: DiaryRepository,
        ingredient_repository: IngredientRepository,
        dish_repository: DishRepository,
        nutrition_goal_repository: NutritionGoalRepository,
    ) -> None:
        self._repository = repository
        self._ingredients = ingredient_repository
        self._dishes = dish_repository
        self._nutrition_goals = nutrition_goal_repository

    async def add_ingredient(
        self,
        *,
        user_id: int,
        ingredient_id: int,
        grams: Decimal,
        meal_type: MealType,
        entry_date: date,
    ) -> DiaryEntry:
        preview = await self.preview_ingredient(user_id, ingredient_id, grams)
        return await self._repository.create(
            user_id=user_id,
            entry_date=entry_date,
            entry_type=DiaryEntryType.INGREDIENT,
            ingredient_id=ingredient_id,
            dish_id=None,
            source_name=preview.source_name,
            grams=grams,
            meal_type=meal_type,
            **self._snapshot_values(preview.nutrition),
        )

    async def add_dish(
        self,
        *,
        user_id: int,
        dish_id: int,
        grams: Decimal,
        meal_type: MealType,
        entry_date: date,
    ) -> DiaryEntry:
        preview = await self.preview_dish(user_id, dish_id, grams)
        return await self._repository.create(
            user_id=user_id,
            entry_date=entry_date,
            entry_type=DiaryEntryType.DISH,
            ingredient_id=None,
            dish_id=dish_id,
            source_name=preview.source_name,
            grams=grams,
            meal_type=meal_type,
            **self._snapshot_values(preview.nutrition),
        )

    async def preview_ingredient(
        self,
        user_id: int,
        ingredient_id: int,
        grams: Decimal,
    ) -> DiaryPreview:
        parse_entry_grams(str(grams))
        ingredient = await self._ingredients.get_by_id(ingredient_id, user_id)
        if ingredient is None:
            raise NotFoundError("Ингредиент не найден.")
        nutrition = NutritionService.calculate_ingredient_nutrition(
            kcal_per_100g=ingredient.kcal_per_100g,
            protein_per_100g=ingredient.protein_per_100g,
            fat_per_100g=ingredient.fat_per_100g,
            carbs_per_100g=ingredient.carbs_per_100g,
            grams=grams,
        )
        return DiaryPreview(
            source_name=ingredient.name,
            grams=grams,
            nutrition=nutrition,
        )

    async def preview_dish(
        self,
        user_id: int,
        dish_id: int,
        grams: Decimal,
    ) -> DiaryPreview:
        parse_entry_grams(str(grams))
        record = await self._dishes.get_by_id(dish_id, user_id)
        if record is None:
            raise NotFoundError("Блюдо не найдено.")
        return DiaryPreview(
            source_name=record.dish.name,
            grams=grams,
            nutrition=self._calculate_dish_portion(record, grams),
        )

    async def get(self, user_id: int, entry_id: int) -> DiaryEntry:
        entry = await self._repository.get_by_id(entry_id, user_id)
        if entry is None:
            raise NotFoundError("Запись рациона не найдена.")
        return entry

    async def get_day(self, user_id: int, entry_date: date) -> DaySummary:
        entries = await self._repository.list_by_date(user_id, entry_date)
        totals = NutritionService.sum_nutrition(
            self._nutrition_from_entry(entry) for entry in entries
        )
        percentages = NutritionService.calculate_macro_percentages(
            protein=totals.protein,
            fat=totals.fat,
            carbs=totals.carbs,
        )
        nutrition_goal = await self._nutrition_goals.get_for_date(
            user_id,
            entry_date,
        )
        return DaySummary(
            entry_date=entry_date,
            entries=entries,
            totals=totals,
            macro_percentages=percentages,
            nutrition_goal=nutrition_goal,
        )

    async def list_page(
        self,
        user_id: int,
        entry_date: date,
        page: int,
    ) -> DiaryEntryPage:
        total = await self._repository.count_by_date(user_id, entry_date)
        pages = max(1, ceil(total / DIARY_ENTRIES_PAGE_SIZE))
        current_page = min(max(page, 1), pages)
        items = await self._repository.list_by_date_page(
            user_id,
            entry_date,
            limit=DIARY_ENTRIES_PAGE_SIZE,
            offset=(current_page - 1) * DIARY_ENTRIES_PAGE_SIZE,
        )
        return DiaryEntryPage(
            items=items,
            page=current_page,
            pages=pages,
            total=total,
        )

    async def update_grams(
        self,
        user_id: int,
        entry_id: int,
        grams: Decimal,
    ) -> DiaryEntry:
        entry = await self.get(user_id, entry_id)
        values = await self._grams_update_values(user_id, entry, grams)
        updated = await self._repository.update(
            entry_id,
            user_id,
            values,
        )
        if updated is None:
            raise NotFoundError("Запись рациона не найдена.")
        return updated

    async def update_entry(
        self,
        user_id: int,
        entry_id: int,
        *,
        expected_updated_at: datetime,
        grams: Decimal | None = None,
        meal_type: MealType | None = None,
        entry_date: date | None = None,
    ) -> DiaryEntry:
        entry = await self.get(user_id, entry_id)
        if entry.updated_at != expected_updated_at:
            raise StaleDataError(
                "Запись уже изменена. Обновите рацион и повторите действие."
            )
        values: dict[str, object] = {}
        if grams is not None and grams != entry.grams:
            values.update(await self._grams_update_values(user_id, entry, grams))
        if meal_type is not None:
            values["meal_type"] = meal_type
        if entry_date is not None:
            values["entry_date"] = entry_date
        if not values:
            return entry
        updated = await self._repository.update_if_current(
            entry_id,
            user_id,
            expected_updated_at,
            values,
        )
        if updated is None:
            if await self._repository.get_by_id(entry_id, user_id) is None:
                raise NotFoundError("Запись рациона не найдена.")
            raise StaleDataError(
                "Запись уже изменена. Обновите рацион и повторите действие."
            )
        return updated

    async def copy_entry(
        self,
        user_id: int,
        entry_id: int,
        *,
        entry_date: date,
        meal_type: MealType | None = None,
    ) -> DiaryEntry:
        entry = await self.get(user_id, entry_id)
        return await self._repository.create(
            user_id=user_id,
            entry_date=entry_date,
            entry_type=entry.entry_type,
            ingredient_id=entry.ingredient_id,
            dish_id=entry.dish_id,
            source_name=entry.source_name,
            grams=entry.grams,
            meal_type=meal_type or entry.meal_type,
            kcal_snapshot=entry.kcal_snapshot,
            protein_snapshot=entry.protein_snapshot,
            fat_snapshot=entry.fat_snapshot,
            carbs_snapshot=entry.carbs_snapshot,
        )

    async def _grams_update_values(
        self,
        user_id: int,
        entry: DiaryEntry,
        grams: Decimal,
    ) -> dict[str, object]:
        parse_entry_grams(str(grams))
        if entry.entry_type is DiaryEntryType.INGREDIENT:
            if entry.ingredient_id is None:
                raise ValidationError(
                    "Исходный ингредиент удален. Изменить граммы нельзя."
                )
            ingredient = await self._ingredients.get_by_id(
                entry.ingredient_id,
                user_id,
            )
            if ingredient is None:
                raise ValidationError(
                    "Исходный ингредиент удален. Изменить граммы нельзя."
                )
            name = ingredient.name
            nutrition = NutritionService.calculate_ingredient_nutrition(
                kcal_per_100g=ingredient.kcal_per_100g,
                protein_per_100g=ingredient.protein_per_100g,
                fat_per_100g=ingredient.fat_per_100g,
                carbs_per_100g=ingredient.carbs_per_100g,
                grams=grams,
            )
        else:
            if entry.dish_id is None:
                raise ValidationError("Исходное блюдо удалено. Изменить граммы нельзя.")
            record = await self._dishes.get_by_id(entry.dish_id, user_id)
            if record is None:
                raise ValidationError("Исходное блюдо удалено. Изменить граммы нельзя.")
            name = record.dish.name
            nutrition = self._calculate_dish_portion(record, grams)

        return {
            "grams": grams,
            "source_name": name,
            **self._snapshot_values(nutrition),
        }

    async def update_meal(
        self,
        user_id: int,
        entry_id: int,
        meal_type: MealType,
    ) -> DiaryEntry:
        return await self._update_entry(user_id, entry_id, {"meal_type": meal_type})

    async def update_date(
        self,
        user_id: int,
        entry_id: int,
        entry_date: date,
    ) -> DiaryEntry:
        return await self._update_entry(user_id, entry_id, {"entry_date": entry_date})

    async def delete(self, user_id: int, entry_id: int) -> None:
        if not await self._repository.delete(entry_id, user_id):
            raise NotFoundError("Запись рациона не найдена.")

    async def _update_entry(
        self,
        user_id: int,
        entry_id: int,
        values: dict[str, object],
    ) -> DiaryEntry:
        updated = await self._repository.update(entry_id, user_id, values)
        if updated is None:
            raise NotFoundError("Запись рациона не найдена.")
        return updated

    @staticmethod
    def _calculate_dish_portion(
        record: DishRecord,
        grams: Decimal,
    ) -> NutritionValues:
        dish_nutrition = NutritionService.calculate_dish_nutrition(
            NutritionComponent(
                nutrition_per_100g=NutritionValues(
                    kcal=item.ingredient.kcal_per_100g,
                    protein=item.ingredient.protein_per_100g,
                    fat=item.ingredient.fat_per_100g,
                    carbs=item.ingredient.carbs_per_100g,
                ),
                grams=item.grams,
            )
            for item in record.components
        )
        return NutritionService.calculate_ingredient_nutrition(
            kcal_per_100g=dish_nutrition.per_100g.kcal,
            protein_per_100g=dish_nutrition.per_100g.protein,
            fat_per_100g=dish_nutrition.per_100g.fat,
            carbs_per_100g=dish_nutrition.per_100g.carbs,
            grams=grams,
        )

    @staticmethod
    def _nutrition_from_entry(entry: DiaryEntry) -> NutritionValues:
        return NutritionValues(
            kcal=entry.kcal_snapshot,
            protein=entry.protein_snapshot,
            fat=entry.fat_snapshot,
            carbs=entry.carbs_snapshot,
        )

    @staticmethod
    def _snapshot_values(nutrition: NutritionValues) -> dict[str, Decimal]:
        return {
            "kcal_snapshot": nutrition.kcal,
            "protein_snapshot": nutrition.protein,
            "fat_snapshot": nutrition.fat,
            "carbs_snapshot": nutrition.carbs,
        }
