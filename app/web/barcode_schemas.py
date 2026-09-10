from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_serializer


class BarcodeLookupRequest(BaseModel):
    barcode: str = Field(min_length=1, max_length=32)


class BarcodeNutritionResponse(BaseModel):
    energy_kcal: str | None
    protein_g: str | None
    fat_g: str | None
    carbs_g: str | None


class BarcodeLookupResponse(BaseModel):
    barcode: str
    found: bool
    name: str | None
    brand: str | None
    package_weight_g: str | None
    package_quantity: str | None
    package_quantity_unit: str | None
    serving_size: str | None
    nutrition_per_100g: BarcodeNutritionResponse
    photo_url: str | None
    missing_fields: list[str]
    derived_fields: list[str]
    source: Literal["open_food_facts"]
    source_url: str
    confirmation_token: str


class BarcodeIngredientCreateRequest(BaseModel):
    confirmation_token: str = Field(min_length=20, max_length=2048)
    confirmed: Literal[True]
    name: str = Field(min_length=1, max_length=255)
    energy_kcal_per_100g: str = Field(min_length=1, max_length=32)
    protein_g_per_100g: str = Field(min_length=1, max_length=32)
    fat_g_per_100g: str = Field(min_length=1, max_length=32)
    carbs_g_per_100g: str = Field(min_length=1, max_length=32)
    package_weight_g: str | None = Field(default=None, max_length=32)
    photo_url: AnyHttpUrl | None = None
    folder_id: str | None = Field(default=None, pattern=r"^[1-9]\d*$", max_length=20)

    @field_serializer("photo_url")
    def serialize_url(self, value: AnyHttpUrl | None) -> str | None:
        return str(value) if value is not None else None
