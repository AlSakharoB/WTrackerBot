from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_serializer, model_validator

FoodSort = Literal["name_asc", "name_desc", "newest", "oldest"]


class FoodNutritionResponse(BaseModel):
    energy_kcal: str
    protein_g: str
    fat_g: str
    carbs_g: str


class IngredientResponse(BaseModel):
    id: str
    name: str
    nutrition_per_100g: FoodNutritionResponse
    folder_id: str | None = None
    package_weight_g: str | None = None
    photo_url: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    created_at: datetime
    updated_at: datetime


class IngredientListResponse(BaseModel):
    items: list[IngredientResponse]
    next_cursor: str | None


class IngredientCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    energy_kcal_per_100g: str = Field(min_length=1, max_length=32)
    protein_g_per_100g: str = Field(min_length=1, max_length=32)
    fat_g_per_100g: str = Field(min_length=1, max_length=32)
    carbs_g_per_100g: str = Field(min_length=1, max_length=32)
    package_weight_g: str | None = Field(default=None, max_length=32)
    photo_url: AnyHttpUrl | None = None
    source_name: str | None = Field(default=None, max_length=100)
    source_url: AnyHttpUrl | None = None
    folder_id: str | None = Field(default=None, pattern=r"^[1-9]\d*$", max_length=20)

    @field_serializer("photo_url", "source_url")
    def serialize_url(self, value: AnyHttpUrl | None) -> str | None:
        return str(value) if value is not None else None


class IngredientUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    energy_kcal_per_100g: str | None = Field(default=None, min_length=1, max_length=32)
    protein_g_per_100g: str | None = Field(default=None, min_length=1, max_length=32)
    fat_g_per_100g: str | None = Field(default=None, min_length=1, max_length=32)
    carbs_g_per_100g: str | None = Field(default=None, min_length=1, max_length=32)
    package_weight_g: str | None = Field(default=None, max_length=32)
    photo_url: AnyHttpUrl | None = None
    source_name: str | None = Field(default=None, max_length=100)
    source_url: AnyHttpUrl | None = None
    folder_id: str | None = Field(default=None, pattern=r"^[1-9]\d*$", max_length=20)

    @model_validator(mode="after")
    def require_change(self) -> "IngredientUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one editable field must be provided")
        return self


class DishComponentRequest(BaseModel):
    ingredient_id: str = Field(pattern=r"^[1-9]\d*$", max_length=20)
    grams: str = Field(min_length=1, max_length=32)


class DishComponentResponse(BaseModel):
    ingredient: IngredientResponse
    grams: str


class DishResponse(BaseModel):
    id: str
    name: str
    total_weight_g: str
    nutrition_total: FoodNutritionResponse
    nutrition_per_100g: FoodNutritionResponse
    components: list[DishComponentResponse]
    folder_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DishListResponse(BaseModel):
    items: list[DishResponse]
    next_cursor: str | None


class DishCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    components: list[DishComponentRequest] = Field(min_length=1, max_length=100)
    folder_id: str | None = Field(default=None, pattern=r"^[1-9]\d*$", max_length=20)


class DishUpdateRequest(DishCreateRequest):
    pass


class DeleteConsequenceResponse(BaseModel):
    can_delete: bool
    message: str
    dependencies: list[str]


class SharingPackageCreateRequest(BaseModel):
    type: Literal["ingredients", "dishes"]
    item_ids: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_ids(self) -> "SharingPackageCreateRequest":
        if len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError("Items must be unique")
        if any(not item.isdigit() or item.startswith("0") for item in self.item_ids):
            raise ValueError("Items must contain positive ids")
        return self


class SharingPackageResponse(BaseModel):
    id: str
    type: Literal["ingredients", "dishes"]
    item_count: int
    deep_link: str
    telegram_share_url: str
    expires_at: datetime


class SharingIngredientPreview(BaseModel):
    key: str
    name: str
    nutrition_per_100g: FoodNutritionResponse
    conflict_type: str
    existing: IngredientResponse | None


class SharingDishPreview(BaseModel):
    key: str
    name: str
    conflict_type: str
    existing_id: str | None


class SharingPreviewResponse(BaseModel):
    package_id: str
    type: Literal["ingredients", "dishes"]
    item_count: int
    is_owner: bool
    already_imported: bool
    expires_at: datetime
    ingredients: list[SharingIngredientPreview]
    dishes: list[SharingDishPreview]


class SharingImportRequest(BaseModel):
    ingredient_decisions: dict[
        str, Literal["reuse", "copy_with_generated_name", "skip"]
    ] = Field(default_factory=dict)
    dish_decisions: dict[str, Literal["create_copy", "skip"]] = Field(
        default_factory=dict
    )


class SharingImportResponse(BaseModel):
    already_imported: bool
    created_ingredients: int
    created_dishes: int
