from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)

from app.search import normalize_search_text

PAYLOAD_VERSION = 1
NUTRITION_LIMITS = {
    "kcal_per_100g": Decimal("1500"),
    "protein_per_100g": Decimal("100"),
    "fat_per_100g": Decimal("100"),
    "carbs_per_100g": Decimal("100"),
}
MAX_COMPONENT_GRAMS = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class SharePayloadLimits:
    max_items: int = 20
    max_ingredients: int = 100
    max_components: int = 200
    max_payload_bytes: int = 262_144


class SharePayloadLimitError(ValueError):
    """Serialized package exceeds one of the configured sharing limits."""


class SharedIngredient(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str = Field(pattern=r"^i[1-9][0-9]*$", max_length=16)
    name: str
    kcal_per_100g: Decimal
    protein_per_100g: Decimal
    fat_per_100g: Decimal
    carbs_per_100g: Decimal

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name or len(name) > 255 or not normalize_search_text(name):
            raise ValueError("Ingredient name must contain 1 to 255 characters")
        return name

    @field_validator(
        "kcal_per_100g",
        "protein_per_100g",
        "fat_per_100g",
        "carbs_per_100g",
        mode="before",
    )
    @classmethod
    def validate_nutrition_decimal(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> Decimal:
        decimal_value = _parse_decimal_string(value)
        limit = NUTRITION_LIMITS[info.field_name]
        if decimal_value < 0 or decimal_value > limit:
            raise ValueError(f"{info.field_name} is outside the domain limits")
        return decimal_value

    @field_serializer(
        "kcal_per_100g",
        "protein_per_100g",
        "fat_per_100g",
        "carbs_per_100g",
    )
    def serialize_decimal(self, value: Decimal) -> str:
        return format(value, "f")


class SharedDishComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ingredient_key: str = Field(pattern=r"^i[1-9][0-9]*$", max_length=16)
    grams: Decimal

    @field_validator("grams", mode="before")
    @classmethod
    def validate_grams(cls, value: object) -> Decimal:
        grams = _parse_decimal_string(value)
        if grams <= 0 or grams > MAX_COMPONENT_GRAMS:
            raise ValueError("Component grams are outside the domain limits")
        return grams

    @field_serializer("grams")
    def serialize_grams(self, value: Decimal) -> str:
        return format(value, "f")


class SharedDish(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    key: str = Field(pattern=r"^d[1-9][0-9]*$", max_length=16)
    name: str
    components: Annotated[list[SharedDishComponent], Field(min_length=1)]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name or len(name) > 255 or not normalize_search_text(name):
            raise ValueError("Dish name must contain 1 to 255 characters")
        return name

    @model_validator(mode="after")
    def reject_duplicate_components(self) -> SharedDish:
        keys = [component.ingredient_key for component in self.components]
        if len(keys) != len(set(keys)):
            raise ValueError("Dish contains duplicate ingredient keys")
        return self


class IngredientSharePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1] = PAYLOAD_VERSION
    type: Literal["ingredients"] = "ingredients"
    ingredients: Annotated[list[SharedIngredient], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_keys(self) -> IngredientSharePayload:
        _ensure_unique_keys(item.key for item in self.ingredients)
        return self


class DishSharePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal[1] = PAYLOAD_VERSION
    type: Literal["dishes"] = "dishes"
    ingredients: Annotated[list[SharedIngredient], Field(min_length=1)]
    dishes: Annotated[list[SharedDish], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_local_keys(self) -> DishSharePayload:
        ingredient_keys = {item.key for item in self.ingredients}
        if len(ingredient_keys) != len(self.ingredients):
            raise ValueError("Payload contains duplicate ingredient keys")
        _ensure_unique_keys(dish.key for dish in self.dishes)
        referenced_keys = {
            component.ingredient_key
            for dish in self.dishes
            for component in dish.components
        }
        if not referenced_keys.issubset(ingredient_keys):
            raise ValueError("Dish contains a dangling ingredient key")
        return self


SharePayload = IngredientSharePayload | DishSharePayload


def parse_share_payload(payload: object) -> SharePayload:
    if not isinstance(payload, dict):
        raise ValueError("Share payload must be a JSON object")
    version = payload.get("version")
    if isinstance(version, bool) or version != PAYLOAD_VERSION:
        raise ValueError("Unsupported share payload version")
    payload_type = payload.get("type")
    if payload_type == "ingredients":
        return IngredientSharePayload.model_validate(payload)
    if payload_type == "dishes":
        return DishSharePayload.model_validate(payload)
    raise ValueError("Unsupported share payload type")


def serialize_share_payload(payload: SharePayload) -> dict[str, object]:
    serialized = payload.model_dump(mode="json")
    return dict(serialized)


def share_payload_size(payload: SharePayload) -> int:
    compact_json = json.dumps(
        serialize_share_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return len(compact_json.encode("utf-8"))


def validate_share_payload_limits(
    payload: SharePayload,
    limits: SharePayloadLimits,
) -> None:
    item_count = (
        len(payload.ingredients)
        if isinstance(payload, IngredientSharePayload)
        else len(payload.dishes)
    )
    component_count = (
        0
        if isinstance(payload, IngredientSharePayload)
        else sum(len(dish.components) for dish in payload.dishes)
    )
    if item_count > limits.max_items:
        raise SharePayloadLimitError("Too many top-level items in share payload")
    if len(payload.ingredients) > limits.max_ingredients:
        raise SharePayloadLimitError("Too many ingredients in share payload")
    if component_count > limits.max_components:
        raise SharePayloadLimitError("Too many dish components in share payload")
    if share_payload_size(payload) > limits.max_payload_bytes:
        raise SharePayloadLimitError("Share payload is too large")


def _parse_decimal_string(value: object) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise ValueError("Domain decimals must be encoded as strings")
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Invalid decimal value") from error
    if not decimal_value.is_finite():
        raise ValueError("Decimal value must be finite")
    return decimal_value


def _ensure_unique_keys(keys: Iterable[str]) -> None:
    collected = list(keys)
    if len(collected) != len(set(collected)):
        raise ValueError("Payload contains duplicate local keys")
