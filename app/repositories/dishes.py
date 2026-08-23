from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dish import Dish, DishIngredient
from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError
from app.search import DUPLICATE_NAME_CANDIDATE_LIMIT


@dataclass(frozen=True, slots=True)
class DishComponentRecord:
    ingredient: Ingredient
    grams: Decimal


@dataclass(frozen=True, slots=True)
class DishRecord:
    dish: Dish
    components: list[DishComponentRecord]


class DishRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        name: str,
        name_normalized: str,
        components: list[tuple[int, Decimal]],
    ) -> Dish:
        try:
            async with self._session.begin_nested():
                statement = (
                    insert(Dish)
                    .values(
                        user_id=user_id,
                        name=name,
                        name_normalized=name_normalized,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[Dish.user_id, Dish.name_normalized]
                    )
                    .returning(Dish)
                )
                dish = await self._session.scalar(statement)
                if dish is None:
                    raise DuplicateError("Блюдо с таким названием уже существует.")
                await self._session.execute(
                    insert(DishIngredient),
                    [
                        {
                            "dish_id": dish.id,
                            "ingredient_id": ingredient_id,
                            "grams": grams,
                        }
                        for ingredient_id, grams in components
                    ],
                )
                return dish
        except IntegrityError as error:
            raise DuplicateError("Блюдо с таким названием уже существует.") from error

    async def find_similar_names(
        self,
        user_id: int,
        name_normalized: str,
        similarity_threshold: Decimal,
    ) -> list[Dish]:
        similarity = func.similarity(Dish.name_normalized, name_normalized)
        statement = (
            select(Dish)
            .where(
                Dish.user_id == user_id,
                similarity >= float(similarity_threshold),
            )
            .order_by(similarity.desc(), Dish.name_normalized, Dish.id)
            .limit(DUPLICATE_NAME_CANDIDATE_LIMIT)
        )
        return list((await self._session.scalars(statement)).all())

    async def replace(
        self,
        *,
        dish_id: int,
        user_id: int,
        name: str,
        name_normalized: str,
        components: list[tuple[int, Decimal]],
    ) -> Dish | None:
        try:
            async with self._session.begin_nested():
                dish = await self._session.scalar(
                    update(Dish)
                    .where(Dish.id == dish_id, Dish.user_id == user_id)
                    .values(name=name, name_normalized=name_normalized)
                    .returning(Dish)
                    .execution_options(populate_existing=True)
                )
                if dish is None:
                    return None
                await self._session.execute(
                    delete(DishIngredient).where(DishIngredient.dish_id == dish_id)
                )
                await self._session.execute(
                    insert(DishIngredient),
                    [
                        {
                            "dish_id": dish.id,
                            "ingredient_id": ingredient_id,
                            "grams": grams,
                        }
                        for ingredient_id, grams in components
                    ],
                )
                return dish
        except IntegrityError as error:
            raise DuplicateError("Блюдо с таким названием уже существует.") from error

    async def get_by_id(self, dish_id: int, user_id: int) -> DishRecord | None:
        dish = await self._session.scalar(
            select(Dish).where(Dish.id == dish_id, Dish.user_id == user_id)
        )
        if dish is None:
            return None
        rows = await self._session.execute(
            select(Ingredient, DishIngredient.grams)
            .join(
                DishIngredient,
                DishIngredient.ingredient_id == Ingredient.id,
            )
            .where(DishIngredient.dish_id == dish_id)
            .order_by(DishIngredient.id)
        )
        components = [
            DishComponentRecord(ingredient=ingredient, grams=grams)
            for ingredient, grams in rows.all()
        ]
        return DishRecord(dish=dish, components=components)

    async def get_ingredients(
        self,
        user_id: int,
        ingredient_ids: set[int],
    ) -> list[Ingredient]:
        if not ingredient_ids:
            return []
        statement = select(Ingredient).where(
            Ingredient.user_id == user_id,
            Ingredient.id.in_(ingredient_ids),
        )
        return list((await self._session.scalars(statement)).all())

    async def count(self, user_id: int) -> int:
        statement = (
            select(func.count()).select_from(Dish).where(Dish.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)

    async def list(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> list[Dish]:
        statement = (
            select(Dish)
            .where(Dish.user_id == user_id)
            .order_by(Dish.name_normalized, Dish.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.scalars(statement)).all())

    async def delete(self, dish_id: int, user_id: int) -> bool:
        statement = (
            delete(Dish)
            .where(Dish.id == dish_id, Dish.user_id == user_id)
            .returning(Dish.id)
        )
        return await self._session.scalar(statement) is not None
