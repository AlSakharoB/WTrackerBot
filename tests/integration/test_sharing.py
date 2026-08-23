from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ingredient, ShareImport, User
from app.exceptions import NotFoundError, ValidationError
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import ShareRepository
from app.search import normalize_search_text
from app.services.sharing import (
    BatchIngredientAction,
    ExpiredShareLinkError,
    IngredientConflictType,
    IngredientImportResolution,
    InvalidShareLinkError,
    SharingService,
)
from app.sharing.payloads import (
    IngredientSharePayload,
    SharedIngredient,
    SharePayloadLimits,
)


def sharing_service(session: AsyncSession) -> SharingService:
    return SharingService(
        ShareRepository(session),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
        ingredient_repository=IngredientRepository(session),
    )


def ingredient_model(
    user_id: int,
    *,
    name: str = "Куриная грудка",
    kcal: str = "165.00",
) -> Ingredient:
    return Ingredient(
        user_id=user_id,
        name=name,
        name_normalized=normalize_search_text(name),
        kcal_per_100g=Decimal(kcal),
        protein_per_100g=Decimal("31.00"),
        fat_per_100g=Decimal("3.60"),
        carbs_per_100g=Decimal("0.00"),
    )


async def test_share_package_storage_hashes_token_and_isolates_owner(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000001, timezone="Europe/Moscow")
    other = User(telegram_id=9951000002, timezone="Europe/Moscow")
    session.add_all([owner, other])
    await session.flush()
    repository = ShareRepository(session)
    service = SharingService(
        repository,
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
    )
    now = datetime(2026, 8, 23, tzinfo=UTC)
    payload = IngredientSharePayload(
        ingredients=[
            SharedIngredient(
                key="i1",
                name="Куриная грудка",
                kcal_per_100g="165.00",
                protein_per_100g="31.00",
                fat_per_100g="3.60",
                carbs_per_100g="0.00",
            )
        ]
    )

    created = await service.create_package(
        owner.id,
        payload,
        share_text="Поделиться ингредиентом",
        now=now,
    )

    assert created.package.token_hash != created.token
    assert created.token not in str(created.package.payload)
    assert created.package.expires_at == now + timedelta(days=30)
    assert (
        await repository.get_owned_by_id(created.package.id, owner.id)
        is created.package
    )
    assert await repository.get_owned_by_id(created.package.id, other.id) is None


async def test_single_ingredient_snapshot_is_owner_scoped_and_survives_source_delete(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000011, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000012, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)

    with pytest.raises(NotFoundError):
        await service.create_ingredient_package(recipient.id, source.id)

    created = await service.create_ingredient_package(owner.id, source.id)
    source.name = "Изменённое название"
    source.name_normalized = "изменённое название"
    source.kcal_per_100g = Decimal("999")
    await session.flush()

    access = await service.resolve_ingredient_token(created.token, recipient.id)
    assert access.payload.ingredients[0].name == "Куриная грудка"
    assert access.payload.ingredients[0].kcal_per_100g == Decimal("165.00")

    await session.delete(source)
    await session.flush()
    access_after_delete = await service.resolve_ingredient_token(
        created.token,
        recipient.id,
    )
    assert access_after_delete.payload == access.payload


async def test_preview_writes_nothing_and_confirm_import_is_idempotent(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000021, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000022, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)
    created = await service.create_ingredient_package(owner.id, source.id)

    access = await service.resolve_ingredient_token(created.token, recipient.id)
    recipient_ingredients = await session.scalar(
        select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
    )
    imports = await session.scalar(select(func.count(ShareImport.id)))
    assert access.previous_import is None
    assert recipient_ingredients == 0
    assert imports == 0

    imported = await service.import_ingredient(
        created.package.id,
        recipient.id,
        IngredientImportResolution.ADD,
    )
    repeated = await service.import_ingredient(
        created.package.id,
        recipient.id,
        IngredientImportResolution.ADD,
    )

    assert imported.ingredient is not None
    assert imported.ingredient.user_id == recipient.id
    assert imported.import_record.created_ingredients_count == 1  # type: ignore[union-attr]
    assert repeated.already_completed
    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 1
    )
    assert await session.scalar(select(func.count(ShareImport.id))) == 1

    with pytest.raises(ValidationError, match="собственную"):
        await service.import_ingredient(
            created.package.id,
            owner.id,
            IngredientImportResolution.ADD,
        )


async def test_exact_and_name_conflicts_never_overwrite_recipient(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000031, timezone="Europe/Moscow")
    exact_recipient = User(telegram_id=9951000032, timezone="Europe/Moscow")
    conflict_recipient = User(telegram_id=9951000033, timezone="Europe/Moscow")
    session.add_all([owner, exact_recipient, conflict_recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    exact = ingredient_model(exact_recipient.id)
    conflict = ingredient_model(conflict_recipient.id, kcal="170.00")
    first_copy = ingredient_model(
        conflict_recipient.id,
        name="Куриная грудка (копия)",
        kcal="170.00",
    )
    session.add_all([source, exact, conflict, first_copy])
    await session.flush()
    service = sharing_service(session)
    created = await service.create_ingredient_package(owner.id, source.id)

    exact_result = await service.import_ingredient(
        created.package.id,
        exact_recipient.id,
        IngredientImportResolution.ADD,
    )
    assert exact_result.preflight.conflict_type is IngredientConflictType.EXACT_SAME
    assert exact_result.import_record.reused_ingredients_count == 1  # type: ignore[union-attr]

    conflict_result = await service.import_ingredient(
        created.package.id,
        conflict_recipient.id,
        IngredientImportResolution.ADD,
    )
    assert conflict_result.requires_resolution
    assert conflict.kcal_per_100g == Decimal("170.00")
    assert (
        await session.scalar(
            select(func.count(ShareImport.id)).where(
                ShareImport.recipient_user_id == conflict_recipient.id
            )
        )
        == 0
    )

    copied = await service.import_ingredient(
        created.package.id,
        conflict_recipient.id,
        IngredientImportResolution.CREATE_COPY,
    )
    assert copied.ingredient is not None
    assert copied.ingredient.name == "Куриная грудка (копия 2)"
    assert conflict.kcal_per_100g == Decimal("170.00")


async def test_similar_conflict_reuses_duplicate_policy_and_keep_is_safe(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000041, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000042, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id, name="Куриная грудкаа")
    existing = ingredient_model(recipient.id)
    session.add_all([source, existing])
    await session.flush()
    service = sharing_service(session)
    created = await service.create_ingredient_package(owner.id, source.id)

    preflight = await service.preflight_ingredient(
        recipient.id,
        (
            await service.resolve_ingredient_token(created.token, recipient.id)
        ).payload.ingredients[0],
    )
    assert preflight.conflict_type is IngredientConflictType.SIMILAR_CONFLICT

    kept = await service.import_ingredient(
        created.package.id,
        recipient.id,
        IngredientImportResolution.KEEP_MINE,
    )
    assert kept.ingredient is existing
    assert kept.import_record.reused_ingredients_count == 1  # type: ignore[union-attr]
    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 1
    )


async def test_expired_revoked_and_invalid_tokens_are_expected_errors(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000051, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000052, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)

    expired = await service.create_ingredient_package(owner.id, source.id)
    expired.package.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    with pytest.raises(ExpiredShareLinkError):
        await service.resolve_ingredient_token(expired.token, recipient.id)

    revoked = await service.create_ingredient_package(owner.id, source.id)
    with pytest.raises(NotFoundError):
        await service.revoke_package(revoked.package.id, recipient.id)
    await service.revoke_package(revoked.package.id, owner.id)
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(revoked.token, recipient.id)

    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token("sh_invalid", recipient.id)


async def test_batch_snapshot_preflight_import_and_repeat_are_consistent(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000061, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000062, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source_new = ingredient_model(owner.id, name="Овсяные хлопья")
    source_exact = ingredient_model(owner.id, name="Молоко")
    source_conflict = ingredient_model(owner.id, name="Творог")
    recipient_exact = ingredient_model(recipient.id, name="Молоко")
    recipient_conflict = ingredient_model(
        recipient.id,
        name="Творог",
        kcal="220.00",
    )
    session.add_all(
        [
            source_new,
            source_exact,
            source_conflict,
            recipient_exact,
            recipient_conflict,
        ]
    )
    await session.flush()
    service = sharing_service(session)

    created = await service.create_ingredient_batch_package(
        owner.id,
        [source_conflict.id, source_new.id, source_exact.id],
    )
    access = await service.resolve_ingredient_token(created.token, recipient.id)
    preflight = await service.preflight_ingredient_batch(recipient.id, access.payload)

    assert [item.name for item in access.payload.ingredients] == [
        "Творог",
        "Овсяные хлопья",
        "Молоко",
    ]
    assert preflight.new_count == 1
    assert preflight.exact_count == 1
    assert preflight.conflict_count == 1

    imported = await service.import_ingredient_batch(
        created.package.id,
        recipient.id,
        {},
    )
    repeated = await service.import_ingredient_batch(
        created.package.id,
        recipient.id,
        {},
    )

    assert imported.import_record.created_ingredients_count == 1
    assert imported.import_record.reused_ingredients_count == 1
    assert imported.import_record.skipped_ingredients_count == 1
    assert repeated.already_completed
    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 3
    )
    assert (
        await session.scalar(
            select(func.count(ShareImport.id)).where(
                ShareImport.package_id == created.package.id,
                ShareImport.recipient_user_id == recipient.id,
            )
        )
        == 1
    )


async def test_batch_copy_resolution_and_source_validation(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000071, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000072, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id, name="Творог")
    existing = ingredient_model(recipient.id, name="Творог", kcal="220.00")
    session.add_all([source, existing])
    await session.flush()
    service = sharing_service(session)

    with pytest.raises(NotFoundError, match="недоступен"):
        await service.create_ingredient_batch_package(owner.id, [existing.id])

    created = await service.create_ingredient_batch_package(owner.id, [source.id])
    imported = await service.import_ingredient_batch(
        created.package.id,
        recipient.id,
        {"i1": BatchIngredientAction.COPY_WITH_GENERATED_NAME.value},
    )

    assert imported.import_record.created_ingredients_count == 1
    assert imported.created_ingredients[0].name == "Творог (копия)"
    await session.delete(source)
    await session.flush()
    with pytest.raises(NotFoundError, match="недоступен"):
        await service.create_ingredient_batch_package(owner.id, [source.id])


async def test_batch_import_rolls_back_all_rows_on_failure(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = User(telegram_id=9951000081, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000082, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    first = ingredient_model(owner.id, name="Первый продукт")
    second = ingredient_model(owner.id, name="Второй продукт")
    session.add_all([first, second])
    await session.flush()
    service = sharing_service(session)
    created = await service.create_ingredient_batch_package(
        owner.id, [first.id, second.id]
    )
    original_create = service._create_imported_ingredient
    calls = 0

    async def fail_on_second(user_id: int, incoming: SharedIngredient) -> Ingredient:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("forced batch failure")
        return await original_create(user_id, incoming)

    monkeypatch.setattr(service, "_create_imported_ingredient", fail_on_second)

    with pytest.raises(RuntimeError, match="forced batch failure"):
        async with session.begin_nested():
            await service.import_ingredient_batch(created.package.id, recipient.id, {})

    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(ShareImport.id)).where(
                ShareImport.package_id == created.package.id,
                ShareImport.recipient_user_id == recipient.id,
            )
        )
        == 0
    )
