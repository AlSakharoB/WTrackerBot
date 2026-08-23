from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.db.models.share import SharePackage, SharePackageType
from app.exceptions import ValidationError
from app.repositories.shares import ShareTokenHashCollisionError
from app.services.sharing import SharingService
from app.sharing.links import build_share_deep_link, build_telegram_share_url
from app.sharing.payloads import (
    DishSharePayload,
    IngredientSharePayload,
    SharedDish,
    SharedDishComponent,
    SharedIngredient,
    SharePayloadLimitError,
    SharePayloadLimits,
    parse_share_payload,
    serialize_share_payload,
    validate_share_payload_limits,
)
from app.sharing.tokens import (
    TELEGRAM_START_PARAMETER_MAX_LENGTH,
    generate_share_token,
    hash_share_token,
    is_valid_share_token,
)


def ingredient(
    key: str = "i1",
    *,
    name: str = "Куриная грудка",
) -> SharedIngredient:
    return SharedIngredient(
        key=key,
        name=name,
        kcal_per_100g=Decimal("165.00"),
        protein_per_100g=Decimal("31.00"),
        fat_per_100g=Decimal("3.60"),
        carbs_per_100g=Decimal("0.00"),
    )


def test_share_tokens_are_secure_urlsafe_and_hashable() -> None:
    tokens = {generate_share_token() for _ in range(100)}

    assert len(tokens) == 100
    for token in tokens:
        assert is_valid_share_token(token)
        assert len(token) <= TELEGRAM_START_PARAMETER_MAX_LENGTH
        assert len(hash_share_token(token)) == 64
        assert hash_share_token(token) != token


def test_ingredient_payload_round_trip_preserves_decimal_strings() -> None:
    payload = IngredientSharePayload(ingredients=[ingredient()])

    serialized = serialize_share_payload(payload)
    restored = parse_share_payload(serialized)

    assert restored == payload
    serialized_ingredient = serialized["ingredients"][0]  # type: ignore[index]
    assert serialized_ingredient["fat_per_100g"] == "3.60"
    assert isinstance(serialized_ingredient["fat_per_100g"], str)


def test_dish_payload_round_trip_resolves_local_ingredient_keys() -> None:
    payload = DishSharePayload(
        ingredients=[ingredient()],
        dishes=[
            SharedDish(
                key="d1",
                name="Курица с гречкой",
                components=[
                    SharedDishComponent(
                        ingredient_key="i1",
                        grams=Decimal("200.00"),
                    )
                ],
            )
        ],
    )

    serialized = serialize_share_payload(payload)

    assert parse_share_payload(serialized) == payload
    component = serialized["dishes"][0]["components"][0]  # type: ignore[index]
    assert component["grams"] == "200.00"


def test_payload_rejects_json_floats_and_unsupported_version() -> None:
    raw = serialize_share_payload(IngredientSharePayload(ingredients=[ingredient()]))
    raw["ingredients"][0]["kcal_per_100g"] = 165.0  # type: ignore[index]

    with pytest.raises(PydanticValidationError, match="encoded as strings"):
        parse_share_payload(raw)

    raw["ingredients"][0]["kcal_per_100g"] = "165.00"  # type: ignore[index]
    raw["version"] = 2
    with pytest.raises(ValueError, match="Unsupported.*version"):
        parse_share_payload(raw)

    raw["version"] = True
    with pytest.raises(ValueError, match="Unsupported.*version"):
        parse_share_payload(raw)


def test_payload_rejects_duplicate_and_dangling_local_keys() -> None:
    with pytest.raises(PydanticValidationError, match="duplicate"):
        IngredientSharePayload(ingredients=[ingredient(), ingredient()])

    with pytest.raises(PydanticValidationError, match="dangling"):
        DishSharePayload(
            ingredients=[ingredient()],
            dishes=[
                SharedDish(
                    key="d1",
                    name="Блюдо",
                    components=[
                        SharedDishComponent(
                            ingredient_key="i2",
                            grams=Decimal("100"),
                        )
                    ],
                )
            ],
        )


@pytest.mark.parametrize(
    "limits",
    [
        SharePayloadLimits(max_items=1),
        SharePayloadLimits(max_ingredients=1),
        SharePayloadLimits(max_components=1),
        SharePayloadLimits(max_payload_bytes=10),
    ],
)
def test_payload_limits_are_enforced(limits: SharePayloadLimits) -> None:
    ingredients = [ingredient("i1"), ingredient("i2", name="Гречка")]
    payload = DishSharePayload(
        ingredients=ingredients,
        dishes=[
            SharedDish(
                key="d1",
                name="Первое блюдо",
                components=[
                    SharedDishComponent(ingredient_key="i1", grams=Decimal("100")),
                    SharedDishComponent(ingredient_key="i2", grams=Decimal("50")),
                ],
            ),
            SharedDish(
                key="d2",
                name="Второе блюдо",
                components=[
                    SharedDishComponent(ingredient_key="i1", grams=Decimal("75"))
                ],
            ),
        ],
    )

    with pytest.raises(SharePayloadLimitError):
        validate_share_payload_limits(payload, limits)


def test_telegram_links_are_encoded_and_username_is_normalized() -> None:
    token = generate_share_token()
    deep_link = build_share_deep_link("@nutrition_test_bot", token)
    share_url = build_telegram_share_url(deep_link, "Курица & гречка")

    assert deep_link == f"https://t.me/nutrition_test_bot?start={token}"
    query = parse_qs(urlparse(share_url).query)
    assert query == {"url": [deep_link], "text": ["Курица & гречка"]}


async def test_sharing_service_stores_only_hash_and_retries_collision() -> None:
    repository = Mock()
    package = SharePackage(id=1, owner_user_id=10)
    repository.create_package = AsyncMock(
        side_effect=[ShareTokenHashCollisionError(), package]
    )
    tokens = iter(
        [
            "sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            "sh_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
        ]
    )
    service = SharingService(
        repository,
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
        token_factory=lambda: next(tokens),
    )
    now = datetime(2026, 8, 23, tzinfo=UTC)

    result = await service.create_package(
        10,
        IngredientSharePayload(ingredients=[ingredient()]),
        share_text="Поделиться",
        now=now,
    )

    assert repository.create_package.await_count == 2
    stored = repository.create_package.await_args.kwargs
    assert stored["token_hash"] == hash_share_token(result.token)
    assert result.token not in str(stored)
    assert stored["package_type"] is SharePackageType.INGREDIENTS
    assert stored["expires_at"] == now + timedelta(days=30)


async def test_sharing_service_rejects_link_creation_without_bot_username() -> None:
    repository = Mock(create_package=AsyncMock())
    service = SharingService(
        repository,
        bot_username=None,
        link_ttl_days=30,
        limits=SharePayloadLimits(),
    )

    with pytest.raises(ValidationError, match="недоступны"):
        await service.create_package(
            10,
            IngredientSharePayload(ingredients=[ingredient()]),
            share_text="Поделиться",
        )

    repository.create_package.assert_not_awaited()
