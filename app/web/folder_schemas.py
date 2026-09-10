from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

FoodItemType = Literal["ingredient", "dish"]


class FoodFolderResponse(BaseModel):
    id: str
    name: str
    sort_order: int
    item_count: int
    ingredient_count: int
    dish_count: int
    created_at: datetime
    updated_at: datetime


class FoodFolderListResponse(BaseModel):
    items: list[FoodFolderResponse]


class FoodFolderCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class FoodFolderUpdateRequest(FoodFolderCreateRequest):
    pass


class FoodFolderReorderRequest(BaseModel):
    folder_ids: list[str] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_ids(self) -> "FoodFolderReorderRequest":
        if any(
            not value.isdigit() or value.startswith("0") for value in self.folder_ids
        ):
            raise ValueError("Folder ids must be positive integers")
        return self


class FoodItemFolderRequest(BaseModel):
    folder_id: str | None = Field(default=None, pattern=r"^[1-9]\d*$", max_length=20)


class FoodItemFolderBatchRequest(FoodItemFolderRequest):
    type: FoodItemType
    item_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_ids(self) -> "FoodItemFolderBatchRequest":
        if len(self.item_ids) != len(set(self.item_ids)) or any(
            not value.isdigit() or value.startswith("0") for value in self.item_ids
        ):
            raise ValueError("Item ids must be unique positive integers")
        return self


class FoodItemFolderResponse(BaseModel):
    type: FoodItemType
    item_ids: list[str]
    folder_id: str | None
