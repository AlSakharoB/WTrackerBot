from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String,
    column,
    delete,
    exists,
    func,
    select,
    true,
    update,
    values,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dish import Dish, DishIngredient
from app.db.models.food_folder import FoodFolderItem
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

    async def find_matches_for_names(
        self,
        user_id: int,
        normalized_names: set[str],
        similarity_threshold: Decimal,
    ) -> dict[str, list[Dish]]:
        if not normalized_names:
            return {}
        incoming = (
            values(
                column("incoming_name", String),
                name="incoming_dish_names",
            )
            .data([(name,) for name in sorted(normalized_names)])
            .cte()
        )
        similarity = func.similarity(
            Dish.name_normalized,
            incoming.c.incoming_name,
        )
        candidates = (
            select(
                Dish.id.label("dish_id"),
                similarity.label("similarity"),
            )
            .select_from(Dish)
            .where(
                Dish.user_id == user_id,
                similarity >= float(similarity_threshold),
            )
            .order_by(similarity.desc(), Dish.name_normalized, Dish.id)
            .limit(DUPLICATE_NAME_CANDIDATE_LIMIT)
            .correlate(incoming)
            .lateral("candidate_dishes")
        )
        statement = (
            select(incoming.c.incoming_name, Dish)
            .select_from(incoming)
            .join(candidates, true())
            .join(
                Dish,
                Dish.id == candidates.c.dish_id,
            )
            .order_by(
                incoming.c.incoming_name,
                candidates.c.similarity.desc(),
                Dish.name_normalized,
                Dish.id,
            )
        )
        matches = {name: [] for name in normalized_names}
        for incoming_name, dish in (await self._session.execute(statement)).all():
            matches[str(incoming_name)].append(dish)
        return matches

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

    async def get_by_ids(
        self,
        dish_ids: set[int],
        user_id: int,
    ) -> list[DishRecord]:
        if not dish_ids:
            return []
        dishes = list(
            (
                await self._session.scalars(
                    select(Dish).where(
                        Dish.id.in_(dish_ids),
                        Dish.user_id == user_id,
                    )
                )
            ).all()
        )
        if not dishes:
            return []
        rows = await self._session.execute(
            select(DishIngredient.dish_id, Ingredient, DishIngredient.grams)
            .join(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
            .where(DishIngredient.dish_id.in_({dish.id for dish in dishes}))
            .order_by(DishIngredient.dish_id, DishIngredient.id)
        )
        components_by_dish: dict[int, list[DishComponentRecord]] = {
            dish.id: [] for dish in dishes
        }
        for dish_id, ingredient, grams in rows.all():
            components_by_dish[dish_id].append(
                DishComponentRecord(ingredient=ingredient, grams=grams)
            )
        return [
            DishRecord(dish=dish, components=components_by_dish[dish.id])
            for dish in dishes
        ]

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

    async def search_records(
        self,
        user_id: int,
        *,
        query: str | None,
        limit: int,
    ) -> list[DishRecord]:
        statement = select(Dish).where(Dish.user_id == user_id)
        if query:
            statement = statement.where(
                Dish.name_normalized.contains(query, autoescape=True)
            )
        dishes = list(
            (
                await self._session.scalars(
                    statement.order_by(Dish.name_normalized, Dish.id).limit(limit)
                )
            ).all()
        )
        by_id = {
            record.dish.id: record
            for record in await self.get_by_ids(
                {dish.id for dish in dishes},
                user_id,
            )
        }
        return [by_id[dish.id] for dish in dishes if dish.id in by_id]

    async def search_records_cursor(
        self,
        user_id: int,
        *,
        query: str | None,
        sort: str,
        cursor_name: str | None,
        cursor_created_at: datetime | None,
        cursor_id: int | None,
        limit: int,
        folder_id: int | None = None,
        unfiled: bool = False,
    ) -> list[DishRecord]:
        statement = select(Dish).where(Dish.user_id == user_id)
        assignment = (
            select(FoodFolderItem.id)
            .where(
                FoodFolderItem.user_id == user_id,
                FoodFolderItem.dish_id == Dish.id,
            )
            .correlate(Dish)
        )
        if folder_id is not None:
            statement = statement.where(
                exists(assignment.where(FoodFolderItem.folder_id == folder_id))
            )
        elif unfiled:
            statement = statement.where(~exists(assignment))
        if query:
            statement = statement.where(
                Dish.name_normalized.contains(query, autoescape=True)
            )
        if sort == "name_desc":
            if cursor_name is not None and cursor_id is not None:
                statement = statement.where(
                    (Dish.name_normalized < cursor_name)
                    | ((Dish.name_normalized == cursor_name) & (Dish.id < cursor_id))
                )
            ordering = (Dish.name_normalized.desc(), Dish.id.desc())
        elif sort in {"newest", "oldest"}:
            descending = sort == "newest"
            if cursor_created_at is not None and cursor_id is not None:
                comparison = (
                    (Dish.created_at < cursor_created_at)
                    | ((Dish.created_at == cursor_created_at) & (Dish.id < cursor_id))
                    if descending
                    else (Dish.created_at > cursor_created_at)
                    | ((Dish.created_at == cursor_created_at) & (Dish.id > cursor_id))
                )
                statement = statement.where(comparison)
            ordering = (
                (Dish.created_at.desc(), Dish.id.desc())
                if descending
                else (Dish.created_at, Dish.id)
            )
        else:
            if cursor_name is not None and cursor_id is not None:
                statement = statement.where(
                    (Dish.name_normalized > cursor_name)
                    | ((Dish.name_normalized == cursor_name) & (Dish.id > cursor_id))
                )
            ordering = (Dish.name_normalized, Dish.id)
        dishes = list(
            (
                await self._session.scalars(statement.order_by(*ordering).limit(limit))
            ).all()
        )
        records = await self.get_by_ids({dish.id for dish in dishes}, user_id)
        by_id = {record.dish.id: record for record in records}
        return [by_id[dish.id] for dish in dishes if dish.id in by_id]

    async def delete(self, dish_id: int, user_id: int) -> bool:
        statement = (
            delete(Dish)
            .where(Dish.id == dish_id, Dish.user_id == user_id)
            .returning(Dish.id)
        )
        return await self._session.scalar(statement) is not None
