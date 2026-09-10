from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.dish import Dish
from app.db.models.food_folder import FoodFolder, FoodFolderItem
from app.db.models.ingredient import Ingredient
from app.exceptions import DuplicateError


@dataclass(frozen=True, slots=True)
class FoodFolderRecord:
    folder: FoodFolder
    ingredient_count: int
    dish_count: int

    @property
    def item_count(self) -> int:
        return self.ingredient_count + self.dish_count


class FoodFolderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def lock_order(self, user_id: int) -> None:
        await self._session.scalar(select(func.pg_advisory_xact_lock(user_id)))

    async def list(self, user_id: int) -> list[FoodFolderRecord]:
        statement = (
            select(
                FoodFolder,
                func.count(FoodFolderItem.ingredient_id).label("ingredient_count"),
                func.count(FoodFolderItem.dish_id).label("dish_count"),
            )
            .outerjoin(
                FoodFolderItem,
                (FoodFolderItem.user_id == FoodFolder.user_id)
                & (FoodFolderItem.folder_id == FoodFolder.id),
            )
            .where(FoodFolder.user_id == user_id)
            .group_by(FoodFolder.id)
            .order_by(FoodFolder.sort_order, FoodFolder.id)
        )
        return [
            FoodFolderRecord(folder, int(ingredient_count), int(dish_count))
            for folder, ingredient_count, dish_count in (
                await self._session.execute(statement)
            ).all()
        ]

    async def get(self, user_id: int, folder_id: int) -> FoodFolder | None:
        return await self._session.scalar(
            select(FoodFolder).where(
                FoodFolder.user_id == user_id, FoodFolder.id == folder_id
            )
        )

    async def create(
        self, user_id: int, *, name: str, normalized_name: str
    ) -> FoodFolder:
        await self.lock_order(user_id)
        next_order = int(
            await self._session.scalar(
                select(func.coalesce(func.max(FoodFolder.sort_order), -1) + 1).where(
                    FoodFolder.user_id == user_id
                )
            )
            or 0
        )
        statement = (
            insert(FoodFolder)
            .values(
                user_id=user_id,
                name=name,
                normalized_name=normalized_name,
                sort_order=next_order,
            )
            .on_conflict_do_nothing(
                index_elements=[FoodFolder.user_id, FoodFolder.normalized_name]
            )
            .returning(FoodFolder)
        )
        folder = await self._session.scalar(statement)
        if folder is None:
            raise DuplicateError("Папка с таким названием уже существует.")
        return folder

    async def rename(
        self, user_id: int, folder_id: int, *, name: str, normalized_name: str
    ) -> FoodFolder | None:
        statement = (
            update(FoodFolder)
            .where(FoodFolder.user_id == user_id, FoodFolder.id == folder_id)
            .values(
                name=name,
                normalized_name=normalized_name,
                updated_at=func.now(),
            )
            .returning(FoodFolder)
            .execution_options(populate_existing=True)
        )
        try:
            async with self._session.begin_nested():
                return await self._session.scalar(statement)
        except IntegrityError as error:
            raise DuplicateError("Папка с таким названием уже существует.") from error

    async def delete(self, user_id: int, folder_id: int) -> bool:
        await self.lock_order(user_id)
        deleted_order = await self._session.scalar(
            delete(FoodFolder)
            .where(FoodFolder.user_id == user_id, FoodFolder.id == folder_id)
            .returning(FoodFolder.sort_order)
        )
        if deleted_order is None:
            return False
        folder_count = int(
            await self._session.scalar(
                select(func.count())
                .select_from(FoodFolder)
                .where(FoodFolder.user_id == user_id)
            )
            or 0
        )
        await self._session.execute(
            update(FoodFolder)
            .where(
                FoodFolder.user_id == user_id,
                FoodFolder.sort_order > deleted_order,
            )
            .values(sort_order=FoodFolder.sort_order + folder_count + 1)
        )
        await self._session.execute(
            update(FoodFolder)
            .where(
                FoodFolder.user_id == user_id,
                FoodFolder.sort_order > deleted_order + folder_count + 1,
            )
            .values(sort_order=FoodFolder.sort_order - folder_count - 2)
        )
        return True

    async def reorder(self, user_id: int, folder_ids: list[int]) -> None:
        await self.lock_order(user_id)
        # Move to a disjoint range first so the per-user unique order stays valid.
        await self._session.execute(
            update(FoodFolder)
            .where(FoodFolder.user_id == user_id)
            .values(sort_order=FoodFolder.sort_order + len(folder_ids) + 1)
        )
        ordering = case(
            {folder_id: index for index, folder_id in enumerate(folder_ids)},
            value=FoodFolder.id,
        )
        await self._session.execute(
            update(FoodFolder)
            .where(FoodFolder.user_id == user_id, FoodFolder.id.in_(folder_ids))
            .values(sort_order=ordering, updated_at=func.now())
        )

    async def ingredient_folder_ids(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[int, int]:
        if not ingredient_ids:
            return {}
        rows = await self._session.execute(
            select(FoodFolderItem.ingredient_id, FoodFolderItem.folder_id).where(
                FoodFolderItem.user_id == user_id,
                FoodFolderItem.ingredient_id.in_(ingredient_ids),
            )
        )
        return {int(item_id): int(folder_id) for item_id, folder_id in rows.all()}

    async def dish_folder_ids(
        self, user_id: int, dish_ids: list[int]
    ) -> dict[int, int]:
        if not dish_ids:
            return {}
        rows = await self._session.execute(
            select(FoodFolderItem.dish_id, FoodFolderItem.folder_id).where(
                FoodFolderItem.user_id == user_id,
                FoodFolderItem.dish_id.in_(dish_ids),
            )
        )
        return {int(item_id): int(folder_id) for item_id, folder_id in rows.all()}

    async def existing_item_ids(
        self, user_id: int, *, item_type: str, item_ids: set[int]
    ) -> set[int]:
        entity = Ingredient if item_type == "ingredient" else Dish
        return set(
            (
                await self._session.scalars(
                    select(entity.id).where(
                        entity.user_id == user_id, entity.id.in_(item_ids)
                    )
                )
            ).all()
        )

    async def move_items(
        self,
        user_id: int,
        *,
        item_type: str,
        item_ids: list[int],
        folder_id: int | None,
    ) -> None:
        id_column = (
            FoodFolderItem.ingredient_id
            if item_type == "ingredient"
            else FoodFolderItem.dish_id
        )
        if folder_id is None:
            await self._session.execute(
                delete(FoodFolderItem).where(
                    FoodFolderItem.user_id == user_id, id_column.in_(item_ids)
                )
            )
            return
        for item_id in item_ids:
            values = {
                "user_id": user_id,
                "folder_id": folder_id,
                "ingredient_id": item_id if item_type == "ingredient" else None,
                "dish_id": item_id if item_type == "dish" else None,
            }
            statement = insert(FoodFolderItem).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[id_column],
                index_where=id_column.is_not(None),
                set_={"folder_id": folder_id, "user_id": user_id},
            )
            await self._session.execute(statement)
