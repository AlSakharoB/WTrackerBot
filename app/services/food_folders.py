from __future__ import annotations

from app.db.models.food_folder import FoodFolder
from app.exceptions import NotFoundError, ValidationError
from app.repositories.food_folders import FoodFolderRecord, FoodFolderRepository
from app.search import normalize_search_text


class FoodFolderService:
    def __init__(self, repository: FoodFolderRepository) -> None:
        self._repository = repository

    @staticmethod
    def _name_values(value: str) -> tuple[str, str]:
        name = " ".join(value.strip().split())
        normalized = normalize_search_text(name)
        if not normalized:
            raise ValidationError("Введите название папки.")
        if len(name) > 100 or len(normalized) > 100:
            raise ValidationError("Название папки не должно быть длиннее 100 символов.")
        return name, normalized

    async def list(self, user_id: int) -> list[FoodFolderRecord]:
        return await self._repository.list(user_id)

    async def get(self, user_id: int, folder_id: int) -> FoodFolder:
        folder = await self._repository.get(user_id, folder_id)
        if folder is None:
            raise NotFoundError("Папка не найдена.")
        return folder

    async def create(self, user_id: int, name: str) -> FoodFolder:
        display_name, normalized = self._name_values(name)
        return await self._repository.create(
            user_id, name=display_name, normalized_name=normalized
        )

    async def rename(self, user_id: int, folder_id: int, name: str) -> FoodFolder:
        display_name, normalized = self._name_values(name)
        folder = await self._repository.rename(
            user_id,
            folder_id,
            name=display_name,
            normalized_name=normalized,
        )
        if folder is None:
            raise NotFoundError("Папка не найдена.")
        return folder

    async def delete(self, user_id: int, folder_id: int) -> None:
        if not await self._repository.delete(user_id, folder_id):
            raise NotFoundError("Папка не найдена.")

    async def reorder(self, user_id: int, folder_ids: list[int]) -> None:
        await self._repository.lock_order(user_id)
        current = await self._repository.list(user_id)
        current_ids = {record.folder.id for record in current}
        if len(folder_ids) != len(set(folder_ids)) or set(folder_ids) != current_ids:
            raise ValidationError("Передайте все папки ровно по одному разу.")
        await self._repository.reorder(user_id, folder_ids)

    async def move(
        self,
        user_id: int,
        *,
        item_type: str,
        item_ids: list[int],
        folder_id: int | None,
    ) -> None:
        if folder_id is not None:
            await self.get(user_id, folder_id)
        if not item_ids or len(item_ids) != len(set(item_ids)):
            raise ValidationError("Выберите хотя бы одну уникальную позицию.")
        existing = await self._repository.existing_item_ids(
            user_id, item_type=item_type, item_ids=set(item_ids)
        )
        if existing != set(item_ids):
            raise NotFoundError("Одна или несколько позиций не найдены.")
        await self._repository.move_items(
            user_id,
            item_type=item_type,
            item_ids=item_ids,
            folder_id=folder_id,
        )
