from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dish import Dish, DishIngredient
from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError
from app.search import DUPLICATE_NAME_CANDIDATE_LIMIT


class IngredientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        name: str,
        name_normalized: str,
        kcal_per_100g: Decimal,
        protein_per_100g: Decimal,
        fat_per_100g: Decimal,
        carbs_per_100g: Decimal,
    ) -> Ingredient:
        statement = (
            insert(Ingredient)
            .values(
                user_id=user_id,
                name=name,
                name_normalized=name_normalized,
                kcal_per_100g=kcal_per_100g,
                protein_per_100g=protein_per_100g,
                fat_per_100g=fat_per_100g,
                carbs_per_100g=carbs_per_100g,
            )
            .on_conflict_do_nothing(
                index_elements=[Ingredient.user_id, Ingredient.name_normalized]
            )
            .returning(Ingredient)
        )
        ingredient = await self._session.scalar(statement)
        if ingredient is None:
            raise DuplicateError("Ингредиент с таким названием уже существует.")
        return ingredient

    async def get_by_id(self, ingredient_id: int, user_id: int) -> Ingredient | None:
        statement = select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.user_id == user_id,
        )
        return await self._session.scalar(statement)

    async def get_by_normalized_name(
        self,
        user_id: int,
        name_normalized: str,
    ) -> Ingredient | None:
        statement = select(Ingredient).where(
            Ingredient.user_id == user_id,
            Ingredient.name_normalized == name_normalized,
        )
        return await self._session.scalar(statement)

    async def find_similar_names(
        self,
        user_id: int,
        name_normalized: str,
        similarity_threshold: Decimal,
    ) -> list[Ingredient]:
        similarity = func.similarity(Ingredient.name_normalized, name_normalized)
        statement = (
            select(Ingredient)
            .where(
                Ingredient.user_id == user_id,
                similarity >= float(similarity_threshold),
            )
            .order_by(similarity.desc(), Ingredient.name_normalized, Ingredient.id)
            .limit(DUPLICATE_NAME_CANDIDATE_LIMIT)
        )
        return list((await self._session.scalars(statement)).all())

    async def count(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Ingredient)
            .where(Ingredient.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)

    async def list(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[Ingredient]:
        statement = (
            select(Ingredient)
            .where(Ingredient.user_id == user_id)
            .order_by(Ingredient.name_normalized, Ingredient.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def update(
        self,
        ingredient_id: int,
        user_id: int,
        values: dict[str, str | Decimal],
    ) -> Ingredient | None:
        statement = (
            update(Ingredient)
            .where(
                Ingredient.id == ingredient_id,
                Ingredient.user_id == user_id,
            )
            .values(**values)
            .returning(Ingredient)
            .execution_options(populate_existing=True)
        )
        try:
            async with self._session.begin_nested():
                return await self._session.scalar(statement)
        except IntegrityError as error:
            raise DuplicateError(
                "Ингредиент с таким названием уже существует."
            ) from error

    async def get_usage_dish_names(
        self,
        ingredient_id: int,
        user_id: int,
    ) -> list[str]:
        statement = (
            select(Dish.name)
            .join(DishIngredient, DishIngredient.dish_id == Dish.id)
            .where(
                DishIngredient.ingredient_id == ingredient_id,
                Dish.user_id == user_id,
            )
            .order_by(Dish.name_normalized)
        )
        return list((await self._session.scalars(statement)).all())

    async def delete(self, ingredient_id: int, user_id: int) -> bool:
        statement = (
            delete(Ingredient)
            .where(
                Ingredient.id == ingredient_id,
                Ingredient.user_id == user_id,
            )
            .returning(Ingredient.id)
        )
        return await self._session.scalar(statement) is not None
