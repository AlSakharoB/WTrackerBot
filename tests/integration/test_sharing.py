import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Dish,
    DishIngredient,
    Ingredient,
    ShareImport,
    SharePackage,
    User,
)
from app.db.models.share import SharePackageType
from app.db.session import create_database_engine, create_session_factory
from app.exceptions import NotFoundError, ValidationError
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import ShareRepository
from app.search import normalize_search_text
from app.services.sharing import (
    BatchIngredientAction,
    DishImportAction,
    ExpiredShareLinkError,
    IngredientConflictType,
    IngredientImportResolution,
    InvalidShareLinkError,
    ShareCleanupService,
    ShareRuntimeStatus,
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
        dish_repository=DishRepository(session),
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


async def dish_model(
    session: AsyncSession,
    user_id: int,
    name: str,
    components: list[tuple[Ingredient, str]],
) -> Dish:
    dish = Dish(
        user_id=user_id,
        name=name,
        name_normalized=normalize_search_text(name),
    )
    session.add(dish)
    await session.flush()
    session.add_all(
        DishIngredient(
            dish_id=dish.id,
            ingredient_id=ingredient.id,
            grams=Decimal(grams),
        )
        for ingredient, grams in components
    )
    await session.flush()
    return dish


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
    with pytest.raises(InvalidShareLinkError) as revoked_error:
        await service.resolve_ingredient_token(revoked.token, recipient.id)

    with pytest.raises(InvalidShareLinkError) as unknown_error:
        await service.resolve_ingredient_token("sh_invalid", recipient.id)
    assert str(revoked_error.value) == str(unknown_error.value)


async def test_database_payload_is_revalidated_before_every_read(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000057, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000058, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)

    unsupported = await service.create_ingredient_package(owner.id, source.id)
    unsupported.package.payload_version = 2
    await session.flush()
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(unsupported.token, recipient.id)

    malformed = await service.create_ingredient_package(owner.id, source.id)
    malformed.package.payload = {
        "version": 1,
        "type": "ingredients",
        "ingredients": [
            {
                "key": "i1",
                "name": "Bad",
                "kcal_per_100g": 100.0,
                "protein_per_100g": "1",
                "fat_per_100g": "1",
                "carbs_per_100g": "1",
            }
        ],
    }
    await session.flush()
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(malformed.token, recipient.id)

    oversized = await service.create_ingredient_package(owner.id, source.id)
    oversized.package.payload = oversized.package.payload | {"unexpected": "x" * 2048}
    await session.flush()
    strict_size_service = SharingService(
        ShareRepository(session),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(max_payload_bytes=1024),
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )
    with pytest.raises(InvalidShareLinkError):
        await strict_size_service.resolve_ingredient_token(
            oversized.token,
            recipient.id,
        )


async def test_concurrent_imports_are_serialized_per_package_and_recipient() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    telegram_ids = [9951000301, 9951000302, 9951000303, 9951000304]
    try:
        async with session_factory() as setup_session, setup_session.begin():
            await setup_session.execute(
                delete(User).where(User.telegram_id.in_(telegram_ids))
            )
            owner = User(telegram_id=telegram_ids[0], timezone="Europe/Moscow")
            recipients = [
                User(telegram_id=telegram_id, timezone="Europe/Moscow")
                for telegram_id in telegram_ids[1:]
            ]
            setup_session.add_all([owner, *recipients])
            await setup_session.flush()
            source = ingredient_model(owner.id)
            setup_session.add(source)
            await setup_session.flush()
            setup_service = sharing_service(setup_session)
            same_recipient_package = await setup_service.create_ingredient_package(
                owner.id,
                source.id,
            )
            multi_recipient_package = await setup_service.create_ingredient_package(
                owner.id,
                source.id,
            )
            same_package_id = same_recipient_package.package.id
            multi_package_id = multi_recipient_package.package.id
            recipient_ids = [recipient.id for recipient in recipients]

        async def import_package(package_id: int, recipient_id: int) -> bool:
            async with session_factory() as import_session, import_session.begin():
                result = await sharing_service(import_session).import_ingredient(
                    package_id,
                    recipient_id,
                    IngredientImportResolution.ADD,
                )
                return result.already_completed

        same_results = await asyncio.gather(
            import_package(same_package_id, recipient_ids[0]),
            import_package(same_package_id, recipient_ids[0]),
        )
        multi_results = await asyncio.gather(
            import_package(multi_package_id, recipient_ids[1]),
            import_package(multi_package_id, recipient_ids[2]),
        )

        assert sorted(same_results) == [False, True]
        assert multi_results == [False, False]
        async with session_factory() as check_session:
            same_imports = await check_session.scalar(
                select(func.count(ShareImport.id)).where(
                    ShareImport.package_id == same_package_id,
                    ShareImport.recipient_user_id == recipient_ids[0],
                )
            )
            multi_imports = await check_session.scalar(
                select(func.count(ShareImport.id)).where(
                    ShareImport.package_id == multi_package_id
                )
            )
            assert same_imports == 1
            assert multi_imports == 2
    finally:
        async with session_factory() as cleanup_session, cleanup_session.begin():
            await cleanup_session.execute(
                delete(User).where(User.telegram_id.in_(telegram_ids))
            )
        await engine.dispose()


async def test_final_import_rechecks_revoke_and_expiry_after_preview(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000305, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000306, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)
    now = datetime(2026, 8, 24, 14, tzinfo=UTC)

    revoked = await service.create_ingredient_package(owner.id, source.id)
    await service.resolve_ingredient_token(revoked.token, recipient.id, now=now)
    await service.revoke_package(revoked.package.id, owner.id, now=now)
    with pytest.raises(InvalidShareLinkError):
        await service.import_ingredient(
            revoked.package.id,
            recipient.id,
            IngredientImportResolution.ADD,
            now=now,
        )

    expired = await service.create_ingredient_package(owner.id, source.id)
    await service.resolve_ingredient_token(expired.token, recipient.id, now=now)
    expired.package.expires_at = now
    await session.flush()
    with pytest.raises(ExpiredShareLinkError):
        await service.import_ingredient(
            expired.package.id,
            recipient.id,
            IngredientImportResolution.ADD,
            now=now,
        )


async def test_owner_management_revoke_rotation_and_import_privacy(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000053, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000054, timezone="Europe/Moscow")
    foreign_owner = User(telegram_id=9951000055, timezone="Europe/Moscow")
    session.add_all([owner, recipient, foreign_owner])
    await session.flush()
    source = ingredient_model(owner.id)
    foreign_source = ingredient_model(foreign_owner.id, name="Молоко")
    session.add_all([source, foreign_source])
    await session.flush()
    service = sharing_service(session)
    now = datetime(2026, 8, 24, 10, tzinfo=UTC)
    created = await service.create_ingredient_package(owner.id, source.id)
    foreign = await service.create_ingredient_package(
        foreign_owner.id, foreign_source.id
    )
    imported = await service.import_ingredient(
        created.package.id,
        recipient.id,
        IngredientImportResolution.ADD,
    )
    imported_ingredient_id = imported.ingredient.id  # type: ignore[union-attr]
    guessed_token = f"sh_{created.package.id:032d}"
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(guessed_token, foreign_owner.id)
    foreign_access = await service.resolve_ingredient_token(
        created.token,
        foreign_owner.id,
    )
    assert foreign_access.package.id == created.package.id
    foreign_import = await service.import_ingredient(
        created.package.id,
        foreign_owner.id,
        IngredientImportResolution.ADD,
    )
    assert foreign_import.ingredient is not None
    assert foreign_import.ingredient.user_id == foreign_owner.id
    with pytest.raises(NotFoundError):
        await service.revoke_package(created.package.id, foreign_owner.id, now=now)

    page = await service.list_owned_packages(
        owner.id,
        SharePackageType.INGREDIENTS,
        now=now,
    )
    assert [item.package.id for item in page.items] == [created.package.id]
    assert page.items[0].completed_imports == 2
    assert page.items[0].runtime_status is ShareRuntimeStatus.ACTIVE
    assert foreign.package.id not in {item.package.id for item in page.items}

    old_token = created.token
    original_payload = created.package.payload.copy()
    await service.revoke_package(created.package.id, owner.id, now=now)
    repeated = await service.revoke_package(created.package.id, owner.id, now=now)
    assert repeated.revoked_at == now
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(old_token, recipient.id, now=now)
    assert await session.get(Ingredient, imported_ingredient_id) is not None

    rotated = await service.rotate_package(created.package.id, owner.id, now=now)
    assert rotated.token != old_token
    assert rotated.package.payload == original_payload
    assert rotated.package.expires_at == now + timedelta(days=30)
    assert rotated.package.revoked_at is None
    with pytest.raises(InvalidShareLinkError):
        await service.resolve_ingredient_token(old_token, recipient.id, now=now)
    access = await service.resolve_ingredient_token(
        rotated.token, recipient.id, now=now
    )
    assert access.package.id == created.package.id
    assert access.previous_import is not None

    with pytest.raises(NotFoundError):
        await service.rotate_package(created.package.id, foreign_owner.id, now=now)


async def test_expiry_boundary_and_cleanup_batch_only_delete_stale_packages(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000056, timezone="Europe/Moscow")
    session.add(owner)
    await session.flush()
    source = ingredient_model(owner.id)
    session.add(source)
    await session.flush()
    service = sharing_service(session)
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)

    stale_expired = await service.create_ingredient_package(owner.id, source.id)
    stale_expired.package.expires_at = now - timedelta(days=30)
    recent_expired = await service.create_ingredient_package(owner.id, source.id)
    recent_expired.package.expires_at = now - timedelta(days=30) + timedelta(seconds=1)
    stale_revoked = await service.create_ingredient_package(owner.id, source.id)
    await service.revoke_package(
        stale_revoked.package.id,
        owner.id,
        now=now - timedelta(days=30),
    )
    recent_revoked = await service.create_ingredient_package(owner.id, source.id)
    await service.revoke_package(
        recent_revoked.package.id,
        owner.id,
        now=now - timedelta(days=30) + timedelta(seconds=1),
    )
    boundary = await service.create_ingredient_package(owner.id, source.id)
    boundary.package.expires_at = now
    await session.flush()

    boundary_item = await service.get_owned_package(
        boundary.package.id,
        owner.id,
        now=now,
    )
    assert boundary_item.runtime_status is ShareRuntimeStatus.EXPIRED

    deleted = await ShareCleanupService(ShareRepository(session)).cleanup_batch(
        retention_days=30,
        batch_size=2,
        now=now,
    )
    assert deleted == 2
    assert await session.get(SharePackage, stale_expired.package.id) is None
    assert await session.get(SharePackage, stale_revoked.package.id) is None
    assert await session.get(SharePackage, recent_expired.package.id) is not None
    assert await session.get(SharePackage, recent_revoked.package.id) is not None
    assert await session.get(SharePackage, boundary.package.id) is not None


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


async def test_dish_snapshot_contains_dependencies_and_survives_source_delete(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000091, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000092, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    chicken = ingredient_model(owner.id, name="Куриная грудка")
    buckwheat = ingredient_model(owner.id, name="Гречка", kcal="330.00")
    session.add_all([chicken, buckwheat])
    await session.flush()
    dish = await dish_model(
        session,
        owner.id,
        "Курица с гречкой",
        [(chicken, "200"), (buckwheat, "150")],
    )
    service = sharing_service(session)

    with pytest.raises(NotFoundError):
        await service.create_dish_package(recipient.id, dish.id)

    created = await service.create_dish_package(owner.id, dish.id)
    access = await service.resolve_dish_token(created.token, recipient.id)
    payload = access.payload

    assert [item.name for item in payload.ingredients] == [
        "Куриная грудка",
        "Гречка",
    ]
    assert [item.ingredient_key for item in payload.dishes[0].components] == [
        "i1",
        "i2",
    ]
    assert [item.grams for item in payload.dishes[0].components] == [
        Decimal("200"),
        Decimal("150"),
    ]

    await session.delete(dish)
    await session.flush()
    await session.delete(chicken)
    await session.delete(buckwheat)
    await session.flush()

    after_delete = await service.resolve_dish_token(created.token, recipient.id)
    assert after_delete.payload == payload


async def test_dish_snapshot_rejects_foreign_component(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000101, timezone="Europe/Moscow")
    other = User(telegram_id=9951000102, timezone="Europe/Moscow")
    session.add_all([owner, other])
    await session.flush()
    foreign = ingredient_model(other.id, name="Чужой ингредиент")
    session.add(foreign)
    await session.flush()
    dish = await dish_model(
        session,
        owner.id,
        "Некорректный рецепт",
        [(foreign, "100")],
    )

    with pytest.raises(NotFoundError, match="недоступен"):
        await sharing_service(session).create_dish_package(owner.id, dish.id)


async def test_dish_import_reuses_exact_and_user_selected_dependency(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000111, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000112, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source_exact = ingredient_model(owner.id, name="Рис", kcal="350.00")
    source_conflict = ingredient_model(owner.id, name="Сыр", kcal="280.00")
    recipient_exact = ingredient_model(recipient.id, name="Рис", kcal="350.00")
    recipient_conflict = ingredient_model(recipient.id, name="Сыр", kcal="350.00")
    session.add_all(
        [source_exact, source_conflict, recipient_exact, recipient_conflict]
    )
    await session.flush()
    source_dish = await dish_model(
        session,
        owner.id,
        "Рис с сыром",
        [(source_exact, "100"), (source_conflict, "100")],
    )
    service = sharing_service(session)
    created = await service.create_dish_package(owner.id, source_dish.id)
    access = await service.resolve_dish_token(created.token, recipient.id)
    preflight = await service.preflight_dish(recipient.id, access.payload)

    assert preflight.ingredients.new_count == 0
    assert preflight.ingredients.exact_count == 1
    assert preflight.ingredients.conflict_count == 1
    with pytest.raises(ValidationError, match="разрешите"):
        await service.import_dish(created.package.id, recipient.id, {}, None)
    assert await session.scalar(select(func.count(ShareImport.id))) == 0

    imported = await service.import_dish(
        created.package.id,
        recipient.id,
        {"i2": BatchIngredientAction.REUSE.value},
        None,
    )
    repeated = await service.import_dish(
        created.package.id,
        recipient.id,
        {"i2": BatchIngredientAction.REUSE.value},
        None,
    )

    assert imported.dish is not None
    assert imported.dish.dish.user_id == recipient.id
    assert {item.ingredient.id for item in imported.dish.components} == {
        recipient_exact.id,
        recipient_conflict.id,
    }
    assert imported.dish.nutrition.total.kcal == Decimal("700.0000")
    assert imported.import_record.created_ingredients_count == 0
    assert imported.import_record.reused_ingredients_count == 2
    assert imported.import_record.created_dishes_count == 1
    assert repeated.already_completed
    assert (
        await session.scalar(
            select(func.count(Dish.id)).where(Dish.user_id == recipient.id)
        )
        == 1
    )


async def test_dish_import_creates_dependency_copy_from_snapshot(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000121, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000122, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id, name="Сыр", kcal="280.00")
    existing = ingredient_model(recipient.id, name="Сыр", kcal="350.00")
    session.add_all([source, existing])
    await session.flush()
    source_dish = await dish_model(
        session,
        owner.id,
        "Сырная тарелка",
        [(source, "120")],
    )
    service = sharing_service(session)
    created = await service.create_dish_package(owner.id, source_dish.id)

    imported = await service.import_dish(
        created.package.id,
        recipient.id,
        {"i1": BatchIngredientAction.COPY_WITH_GENERATED_NAME.value},
        None,
    )

    assert imported.dish is not None
    copied = imported.dish.components[0].ingredient
    assert copied.name == "Сыр (копия)"
    assert copied.kcal_per_100g == Decimal("280.00")
    assert imported.dish.nutrition.total.kcal == Decimal("336.0000")


async def test_single_dish_acceptance_flow_handles_new_exact_and_copy_independently(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000311, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000312, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source_rice = ingredient_model(owner.id, name="Рис", kcal="350.00")
    source_cheese = ingredient_model(owner.id, name="Сыр", kcal="280.00")
    source_herbs = ingredient_model(owner.id, name="Зелень", kcal="50.00")
    recipient_rice = ingredient_model(recipient.id, name="Рис", kcal="350.00")
    recipient_cheese = ingredient_model(recipient.id, name="Сыр", kcal="350.00")
    session.add_all(
        [
            source_rice,
            source_cheese,
            source_herbs,
            recipient_rice,
            recipient_cheese,
        ]
    )
    await session.flush()
    source_dish = await dish_model(
        session,
        owner.id,
        "Рис с сыром и зеленью",
        [
            (source_rice, "100"),
            (source_cheese, "120"),
            (source_herbs, "20"),
        ],
    )
    service = sharing_service(session)

    created = await service.create_dish_package(owner.id, source_dish.id)
    access = await service.resolve_dish_token(created.token, recipient.id)
    preflight = await service.preflight_dish(recipient.id, access.payload)

    assert preflight.ingredients.new_count == 1
    assert preflight.ingredients.exact_count == 1
    assert preflight.ingredients.conflict_count == 1

    imported = await service.import_dish(
        created.package.id,
        recipient.id,
        {"i2": BatchIngredientAction.COPY_WITH_GENERATED_NAME.value},
        None,
    )

    assert imported.dish is not None
    components = {
        component.ingredient.name: component for component in imported.dish.components
    }
    assert components["Рис"].ingredient.id == recipient_rice.id
    assert components["Сыр (копия)"].ingredient.kcal_per_100g == Decimal("280.00")
    assert components["Зелень"].ingredient.user_id == recipient.id
    assert [component.grams for component in imported.dish.components] == [
        Decimal("100"),
        Decimal("120"),
        Decimal("20"),
    ]
    assert imported.dish.nutrition.total.kcal == Decimal("696.0000")
    assert imported.import_record.created_ingredients_count == 2
    assert imported.import_record.reused_ingredients_count == 1
    assert imported.import_record.created_dishes_count == 1
    assert recipient_cheese.kcal_per_100g == Decimal("350.00")

    source_cheese.kcal_per_100g = Decimal("999.00")
    source_dish.name = "Изменённый исходный рецепт"
    await session.flush()

    assert imported.dish.dish.name == "Рис с сыром и зеленью"
    assert components["Сыр (копия)"].ingredient.kcal_per_100g == Decimal("280.00")


async def test_dish_name_conflict_requires_copy_or_safe_skip(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000131, timezone="Europe/Moscow")
    copy_recipient = User(telegram_id=9951000132, timezone="Europe/Moscow")
    skip_recipient = User(telegram_id=9951000133, timezone="Europe/Moscow")
    session.add_all([owner, copy_recipient, skip_recipient])
    await session.flush()
    source = ingredient_model(owner.id, name="Яйцо")
    copy_exact = ingredient_model(copy_recipient.id, name="Яйцо")
    skip_exact = ingredient_model(skip_recipient.id, name="Яйцо")
    session.add_all([source, copy_exact, skip_exact])
    await session.flush()
    source_dish = await dish_model(
        session,
        owner.id,
        "Омлет",
        [(source, "100")],
    )
    existing_copy_dish = await dish_model(
        session,
        copy_recipient.id,
        "Омлет",
        [(copy_exact, "80")],
    )
    existing_skip_dish = await dish_model(
        session,
        skip_recipient.id,
        "Омлет",
        [(skip_exact, "90")],
    )
    service = sharing_service(session)
    created = await service.create_dish_package(owner.id, source_dish.id)

    with pytest.raises(ValidationError, match="разрешите"):
        await service.import_dish(
            created.package.id,
            copy_recipient.id,
            {},
            None,
        )
    copied = await service.import_dish(
        created.package.id,
        copy_recipient.id,
        {},
        DishImportAction.CREATE_COPY.value,
    )
    skipped = await service.import_dish(
        created.package.id,
        skip_recipient.id,
        {},
        DishImportAction.SKIP.value,
    )

    assert copied.dish is not None
    assert copied.dish.dish.name == "Омлет (копия)"
    assert existing_copy_dish.name == "Омлет"
    assert skipped.dish is None
    assert skipped.import_record.skipped_dishes_count == 1
    assert existing_skip_dish.name == "Омлет"


async def test_dish_import_rolls_back_dependencies_and_claim_on_failure(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = User(telegram_id=9951000141, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000142, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    first = ingredient_model(owner.id, name="Первый компонент")
    second = ingredient_model(owner.id, name="Второй компонент")
    session.add_all([first, second])
    await session.flush()
    source_dish = await dish_model(
        session,
        owner.id,
        "Аварийный рецепт",
        [(first, "100"), (second, "200")],
    )
    service = sharing_service(session)
    created = await service.create_dish_package(owner.id, source_dish.id)
    original_create = service._create_imported_ingredient
    calls = 0

    async def fail_on_second(user_id: int, incoming: SharedIngredient) -> Ingredient:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("forced dish failure")
        return await original_create(user_id, incoming)

    monkeypatch.setattr(service, "_create_imported_ingredient", fail_on_second)

    with pytest.raises(RuntimeError, match="forced dish failure"):
        async with session.begin_nested():
            await service.import_dish(created.package.id, recipient.id, {}, None)

    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(Dish.id)).where(Dish.user_id == recipient.id)
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


async def test_dish_batch_snapshot_deduplicates_shared_dependencies(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000151, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000152, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    egg = ingredient_model(owner.id, name="Яйцо")
    cheese = ingredient_model(owner.id, name="Сыр", kcal="280.00")
    session.add_all([egg, cheese])
    await session.flush()
    omelet = await dish_model(
        session,
        owner.id,
        "Омлет",
        [(egg, "100"), (cheese, "20")],
    )
    salad = await dish_model(
        session,
        owner.id,
        "Яичный салат",
        [(egg, "80")],
    )
    service = sharing_service(session)

    created = await service.create_dish_batch_package(
        owner.id,
        [salad.id, omelet.id],
    )
    payload = (await service.resolve_dish_token(created.token, recipient.id)).payload

    assert [dish.name for dish in payload.dishes] == ["Яичный салат", "Омлет"]
    assert [item.name for item in payload.ingredients] == ["Яйцо", "Сыр"]
    egg_key = payload.ingredients[0].key
    assert payload.dishes[0].components[0].ingredient_key == egg_key
    assert payload.dishes[1].components[0].ingredient_key == egg_key
    assert created.package.item_count == 2


async def test_dish_batch_limits_top_level_and_total_components(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000161, timezone="Europe/Moscow")
    session.add(owner)
    await session.flush()
    ingredient = ingredient_model(owner.id, name="Основа")
    session.add(ingredient)
    await session.flush()
    first = await dish_model(session, owner.id, "Первое", [(ingredient, "100")])
    second = await dish_model(session, owner.id, "Второе", [(ingredient, "200")])
    component_limited = SharingService(
        ShareRepository(session),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(max_components=1),
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )
    item_limited = SharingService(
        ShareRepository(session),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(max_items=1),
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )

    with pytest.raises(ValidationError, match="слишком большой"):
        await component_limited.create_dish_batch_package(
            owner.id, [first.id, second.id]
        )
    with pytest.raises(ValidationError, match="не более 1"):
        await item_limited.create_dish_batch_package(owner.id, [first.id, second.id])


async def test_dish_batch_shared_conflict_is_resolved_once_and_idempotent(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000171, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000172, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source_egg = ingredient_model(owner.id, name="Яйцо", kcal="150.00")
    recipient_egg = ingredient_model(recipient.id, name="Яйцо", kcal="170.00")
    session.add_all([source_egg, recipient_egg])
    await session.flush()
    omelet = await dish_model(session, owner.id, "Омлет", [(source_egg, "100")])
    salad = await dish_model(
        session,
        owner.id,
        "Яичный салат",
        [(source_egg, "80")],
    )
    service = sharing_service(session)
    created = await service.create_dish_batch_package(
        owner.id,
        [omelet.id, salad.id],
    )
    access = await service.resolve_dish_token(created.token, recipient.id)
    preflight = await service.preflight_dish_batch(recipient.id, access.payload)

    assert preflight.ingredients.conflict_count == 1
    assert preflight.dish_conflict_count == 0
    imported = await service.import_dish_batch(
        created.package.id,
        recipient.id,
        {"i1": BatchIngredientAction.REUSE.value},
        {},
    )
    repeated = await service.import_dish_batch(
        created.package.id,
        recipient.id,
        {"i1": BatchIngredientAction.REUSE.value},
        {},
    )

    assert imported.import_record.reused_ingredients_count == 1
    assert imported.import_record.created_dishes_count == 2
    assert len(imported.dishes) == 2
    assert all(
        details.components[0].ingredient.id == recipient_egg.id
        for details in imported.dishes
    )
    assert repeated.already_completed
    assert (
        await session.scalar(
            select(func.count(Dish.id)).where(Dish.user_id == recipient.id)
        )
        == 2
    )


async def test_dish_batch_skip_prunes_orphan_dependency(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000181, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000182, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    first_ingredient = ingredient_model(owner.id, name="Первая основа")
    second_ingredient = ingredient_model(owner.id, name="Вторая основа")
    session.add_all([first_ingredient, second_ingredient])
    await session.flush()
    first = await dish_model(
        session,
        owner.id,
        "Первое блюдо",
        [(first_ingredient, "100")],
    )
    second = await dish_model(
        session,
        owner.id,
        "Второе блюдо",
        [(second_ingredient, "100")],
    )
    service = sharing_service(session)
    created = await service.create_dish_batch_package(owner.id, [first.id, second.id])

    imported = await service.import_dish_batch(
        created.package.id,
        recipient.id,
        {},
        {"d2": DishImportAction.SKIP.value},
    )

    assert imported.import_record.created_dishes_count == 1
    assert imported.import_record.skipped_dishes_count == 1
    assert imported.import_record.created_ingredients_count == 1
    assert imported.import_record.skipped_ingredients_count == 1
    recipient_ingredients = list(
        (
            await session.scalars(
                select(Ingredient).where(Ingredient.user_id == recipient.id)
            )
        ).all()
    )
    assert [item.name for item in recipient_ingredients] == ["Первая основа"]


async def test_dish_batch_conflicting_dish_requires_explicit_plan(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000191, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000192, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    source = ingredient_model(owner.id, name="Яйцо")
    exact = ingredient_model(recipient.id, name="Яйцо")
    session.add_all([source, exact])
    await session.flush()
    source_omelet = await dish_model(
        session,
        owner.id,
        "Омлет",
        [(source, "100")],
    )
    source_salad = await dish_model(
        session,
        owner.id,
        "Салат",
        [(source, "50")],
    )
    await dish_model(session, recipient.id, "Омлет", [(exact, "80")])
    service = sharing_service(session)
    created = await service.create_dish_batch_package(
        owner.id,
        [source_omelet.id, source_salad.id],
    )

    with pytest.raises(ValidationError, match="разрешите"):
        await service.import_dish_batch(created.package.id, recipient.id, {}, {})
    imported = await service.import_dish_batch(
        created.package.id,
        recipient.id,
        {},
        {"d1": DishImportAction.SKIP.value},
    )

    assert imported.import_record.created_dishes_count == 1
    assert imported.import_record.skipped_dishes_count == 1
    assert imported.import_record.reused_ingredients_count == 1


async def test_dish_batch_maximum_item_count_builds_deterministic_preflight(
    session: AsyncSession,
) -> None:
    owner = User(telegram_id=9951000201, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000202, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    shared = ingredient_model(owner.id, name="Общая основа")
    session.add(shared)
    await session.flush()
    dishes = [
        await dish_model(
            session,
            owner.id,
            f"Рецепт {index}",
            [(shared, str(50 + index))],
        )
        for index in range(1, 21)
    ]
    service = sharing_service(session)

    created = await service.create_dish_batch_package(
        owner.id,
        [dish.id for dish in dishes],
    )
    access = await service.resolve_dish_token(created.token, recipient.id)
    connection = await session.connection()
    query_count = 0

    def count_query(*_: object) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(connection.sync_connection, "before_cursor_execute", count_query)
    try:
        preflight = await service.preflight_dish_batch(recipient.id, access.payload)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", count_query)

    assert len(access.payload.dishes) == 20
    assert len(access.payload.ingredients) == 1
    assert len(preflight.dishes) == 20
    assert preflight.ingredients.new_count == 1
    assert preflight.dish_conflict_count == 0
    assert query_count == 2


async def test_dish_batch_import_rolls_back_everything_on_failure(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = User(telegram_id=9951000211, timezone="Europe/Moscow")
    recipient = User(telegram_id=9951000212, timezone="Europe/Moscow")
    session.add_all([owner, recipient])
    await session.flush()
    first_ingredient = ingredient_model(owner.id, name="Пакетная основа 1")
    second_ingredient = ingredient_model(owner.id, name="Пакетная основа 2")
    session.add_all([first_ingredient, second_ingredient])
    await session.flush()
    first = await dish_model(
        session,
        owner.id,
        "Пакетный рецепт 1",
        [(first_ingredient, "100")],
    )
    second = await dish_model(
        session,
        owner.id,
        "Пакетный рецепт 2",
        [(second_ingredient, "100")],
    )
    service = sharing_service(session)
    created = await service.create_dish_batch_package(owner.id, [first.id, second.id])
    original_create = service._create_imported_ingredient
    calls = 0

    async def fail_on_second(user_id: int, incoming: SharedIngredient) -> Ingredient:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("forced dish batch failure")
        return await original_create(user_id, incoming)

    monkeypatch.setattr(service, "_create_imported_ingredient", fail_on_second)

    with pytest.raises(RuntimeError, match="forced dish batch failure"):
        async with session.begin_nested():
            await service.import_dish_batch(created.package.id, recipient.id, {}, {})

    assert (
        await session.scalar(
            select(func.count(Ingredient.id)).where(Ingredient.user_id == recipient.id)
        )
        == 0
    )
    assert (
        await session.scalar(
            select(func.count(Dish.id)).where(Dish.user_id == recipient.id)
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
