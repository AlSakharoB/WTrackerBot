from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.db.models import Ingredient
from app.db.models.share import SharePackage, SharePackageType
from app.exceptions import ValidationError
from app.repositories.shares import ShareTokenHashCollisionError
from app.services.sharing import (
    BatchIngredientAction,
    IngredientConflictType,
    IngredientPreflight,
    SharingService,
)
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
    SHARE_TOKEN_BYTES,
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
    assert SHARE_TOKEN_BYTES * 8 >= 192
    for token in tokens:
        assert is_valid_share_token(token)
        assert len(token) <= TELEGRAM_START_PARAMETER_MAX_LENGTH
        assert len(hash_share_token(token)) == 64
        assert hash_share_token(token) != token
        assert "user" not in token


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

    with pytest.raises(PydanticValidationError, match="duplicate"):
        DishSharePayload(
            ingredients=[ingredient()],
            dishes=[
                SharedDish(
                    key="d1",
                    name="Блюдо",
                    components=[
                        SharedDishComponent(ingredient_key="i1", grams=Decimal("100")),
                        SharedDishComponent(ingredient_key="i1", grams=Decimal("200")),
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


async def test_rotation_retries_old_and_colliding_tokens_without_payload_change() -> (
    None
):
    old_token = "sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    payload = serialize_share_payload(
        IngredientSharePayload(ingredients=[ingredient()])
    )
    package = SharePackage(
        id=1,
        owner_user_id=10,
        token_hash=hash_share_token(old_token),
        package_type=SharePackageType.INGREDIENTS,
        payload_version=1,
        payload=payload,
        item_count=1,
        expires_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    repository = Mock()
    repository.get_owned_by_id = AsyncMock(return_value=package)
    repository.rotate_owned = AsyncMock(
        side_effect=[ShareTokenHashCollisionError(), package]
    )
    tokens = iter(
        [
            old_token,
            "sh_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
            "sh_CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
        ]
    )
    service = SharingService(
        repository,
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
        token_factory=lambda: next(tokens),
    )
    now = datetime(2026, 8, 24, tzinfo=UTC)

    result = await service.rotate_package(1, 10, now=now)

    assert result.token.endswith("C" * 32)
    assert repository.rotate_owned.await_count == 2
    assert repository.rotate_owned.await_args.kwargs["expires_at"] == now + timedelta(
        days=30
    )
    assert package.payload == payload


async def test_batch_snapshot_preserves_selected_order_and_rechecks_sources() -> None:
    share_repository = Mock()
    share_repository.create_package = AsyncMock(
        return_value=SharePackage(
            id=12,
            owner_user_id=10,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    first = Ingredient(
        id=1,
        user_id=10,
        name="Первый",
        name_normalized="первый",
        kcal_per_100g=Decimal("1"),
        protein_per_100g=Decimal("2"),
        fat_per_100g=Decimal("3"),
        carbs_per_100g=Decimal("4"),
    )
    second = Ingredient(
        id=2,
        user_id=10,
        name="Второй",
        name_normalized="второй",
        kcal_per_100g=Decimal("5"),
        protein_per_100g=Decimal("6"),
        fat_per_100g=Decimal("7"),
        carbs_per_100g=Decimal("8"),
    )
    ingredient_repository = Mock()
    ingredient_repository.get_by_ids = AsyncMock(return_value=[first, second])
    service = SharingService(
        share_repository,
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(max_items=20),
        ingredient_repository=ingredient_repository,
        token_factory=lambda: "sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    )

    await service.create_ingredient_batch_package(10, [2, 1])

    ingredient_repository.get_by_ids.assert_awaited_once_with({1, 2}, 10)
    stored = share_repository.create_package.await_args.kwargs
    assert [item["name"] for item in stored["payload"]["ingredients"]] == [
        "Второй",
        "Первый",
    ]
    assert stored["item_count"] == 2


@pytest.mark.parametrize(
    ("ingredient_ids", "message"),
    [
        ([], "хотя бы один"),
        ([1, 1], "дважды"),
        (list(range(21)), "не более 20"),
    ],
)
async def test_batch_snapshot_rejects_empty_duplicate_and_oversized_selection(
    ingredient_ids: list[int],
    message: str,
) -> None:
    ingredient_repository = Mock(get_by_ids=AsyncMock())
    service = SharingService(
        Mock(),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(max_items=20),
        ingredient_repository=ingredient_repository,
    )

    with pytest.raises(ValidationError, match=message):
        await service.create_ingredient_batch_package(10, ingredient_ids)

    ingredient_repository.get_by_ids.assert_not_awaited()


async def test_batch_plan_uses_safe_defaults_for_conflicts() -> None:
    incoming_new = ingredient("i1", name="Новый")
    incoming_exact = ingredient("i2", name="Точный")
    incoming_conflict = ingredient("i3", name="Конфликт")
    existing = Ingredient(
        id=5,
        user_id=20,
        name="Конфликт",
        name_normalized="конфликт",
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("10"),
        carbs_per_100g=Decimal("10"),
    )
    service = SharingService(
        Mock(),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
    )
    service.preflight_ingredient_batch = AsyncMock(  # type: ignore[method-assign]
        return_value=sharing_preflight(
            IngredientPreflight(IngredientConflictType.NEW, incoming_new),
            IngredientPreflight(
                IngredientConflictType.EXACT_SAME, incoming_exact, existing
            ),
            IngredientPreflight(
                IngredientConflictType.NAME_CONFLICT, incoming_conflict, existing
            ),
        )
    )
    payload = IngredientSharePayload(
        ingredients=[incoming_new, incoming_exact, incoming_conflict]
    )

    default_plan = await service.build_ingredient_batch_plan(20, payload, {})
    copy_plan = await service.build_ingredient_batch_plan(
        20,
        payload,
        {"i3": BatchIngredientAction.COPY_WITH_GENERATED_NAME.value},
    )

    assert [item.action for item in default_plan.items] == [
        BatchIngredientAction.CREATE,
        BatchIngredientAction.REUSE,
        BatchIngredientAction.SKIP,
    ]
    assert copy_plan.items[-1].action is BatchIngredientAction.COPY_WITH_GENERATED_NAME


def sharing_preflight(*items: IngredientPreflight):
    from app.services.sharing import BatchIngredientPreflight

    return BatchIngredientPreflight(items)
