import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text

from app.db.models import Ingredient, ShareImport, SharePackage, User
from app.db.models.share import SharePackageStatus, SharePackageType
from app.db.session import create_database_engine, create_session_factory
from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.shares import ShareRepository
from app.search import normalize_search_text
from app.services.sharing import (
    IngredientImportResolution,
    ShareCleanupService,
    SharingService,
)
from app.sharing.payloads import SharePayloadLimits, share_payload_size


async def test_database_pool_handles_parallel_simple_operations() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)

    async def select_one() -> int:
        async with engine.connect() as connection:
            return (await connection.execute(text("SELECT 1"))).scalar_one()

    try:
        async with asyncio.timeout(15):
            results = await asyncio.gather(*(select_one() for _ in range(40)))
    finally:
        await engine.dispose()

    assert results == [1] * 40


def _sharing_service(session) -> SharingService:
    return SharingService(
        ShareRepository(session),
        bot_username="nutrition_test_bot",
        link_ttl_days=30,
        limits=SharePayloadLimits(),
        ingredient_repository=IngredientRepository(session),
        dish_repository=DishRepository(session),
    )


def _ingredient(user_id: int, index: int) -> Ingredient:
    name = f"Нагрузочный ингредиент {index}"
    return Ingredient(
        user_id=user_id,
        name=name,
        name_normalized=normalize_search_text(name),
        kcal_per_100g=Decimal("100.00") + index,
        protein_per_100g=Decimal("10.00"),
        fat_per_100g=Decimal("5.00"),
        carbs_per_100g=Decimal("12.00"),
    )


async def test_sharing_load_smoke_covers_preview_import_limits_and_cleanup() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    telegram_ids = list(range(9952000001, 9952000022))
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    expired_count = 250
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
            ingredients = [_ingredient(owner.id, index) for index in range(1, 21)]
            setup_session.add_all(ingredients)
            await setup_session.flush()
            service = _sharing_service(setup_session)
            preview_package = await service.create_ingredient_package(
                owner.id,
                ingredients[0].id,
            )
            double_confirm_package = await service.create_ingredient_package(
                owner.id,
                ingredients[1].id,
            )
            maximum_package = await service.create_ingredient_batch_package(
                owner.id,
                [ingredient.id for ingredient in ingredients],
            )
            expired_payload = maximum_package.package.payload
            setup_session.add_all(
                SharePackage(
                    owner_user_id=owner.id,
                    token_hash=f"{index:064x}",
                    package_type=SharePackageType.INGREDIENTS,
                    payload_version=1,
                    payload=expired_payload,
                    item_count=20,
                    status=SharePackageStatus.ACTIVE,
                    expires_at=now - timedelta(days=61),
                )
                for index in range(1, expired_count + 1)
            )
            await setup_session.flush()
            owner_id = owner.id
            recipient_ids = [recipient.id for recipient in recipients]
            preview_token = preview_package.token
            preview_package_id = preview_package.package.id
            double_package_id = double_confirm_package.package.id
            maximum_token = maximum_package.token

        async def preview(recipient_id: int) -> int:
            async with session_factory() as preview_session:
                access = await _sharing_service(
                    preview_session
                ).resolve_ingredient_token(
                    preview_token,
                    recipient_id,
                )
                return access.package.id

        async with asyncio.timeout(30):
            preview_results = await asyncio.gather(
                *(preview(recipient_ids[index % 20]) for index in range(100))
            )
        assert preview_results == [preview_package_id] * 100

        async with session_factory() as maximum_session:
            maximum_access = await _sharing_service(
                maximum_session
            ).resolve_ingredient_token(maximum_token, recipient_ids[0])
            maximum_preflight = await _sharing_service(
                maximum_session
            ).preflight_ingredient_batch(
                recipient_ids[0],
                maximum_access.payload,
            )
        assert len(maximum_access.payload.ingredients) == 20
        assert maximum_preflight.new_count == 20
        assert share_payload_size(maximum_access.payload) <= 262_144

        async def import_once(package_id: int, recipient_id: int) -> bool:
            async with session_factory() as import_session, import_session.begin():
                result = await _sharing_service(import_session).import_ingredient(
                    package_id,
                    recipient_id,
                    IngredientImportResolution.ADD,
                )
                return result.already_completed

        async with asyncio.timeout(30):
            import_results = await asyncio.gather(
                *(
                    import_once(preview_package_id, recipient_id)
                    for recipient_id in recipient_ids
                )
            )
        assert import_results == [False] * 20

        async with asyncio.timeout(30):
            double_results = await asyncio.gather(
                import_once(double_package_id, recipient_ids[0]),
                import_once(double_package_id, recipient_ids[0]),
            )
        assert sorted(double_results) == [False, True]

        deleted_total = 0
        while True:
            async with session_factory() as cleanup_session, cleanup_session.begin():
                deleted = await ShareCleanupService(
                    ShareRepository(cleanup_session)
                ).cleanup_batch(
                    retention_days=30,
                    batch_size=64,
                    now=now,
                )
            deleted_total += deleted
            if deleted == 0:
                break
        assert deleted_total == expired_count

        async with session_factory() as check_session:
            import_count = await check_session.scalar(
                select(func.count(ShareImport.id)).where(
                    ShareImport.package_id == preview_package_id
                )
            )
            recipient_ingredient_count = await check_session.scalar(
                select(func.count(Ingredient.id)).where(
                    Ingredient.user_id.in_(recipient_ids)
                )
            )
            owner_record = await ShareRepository(check_session).get_owned_record(
                preview_package_id,
                owner_id,
            )
        assert import_count == 20
        assert recipient_ingredient_count == 21
        assert owner_record is not None
        assert owner_record.completed_imports == 20
    finally:
        async with session_factory() as cleanup_session, cleanup_session.begin():
            await cleanup_session.execute(
                delete(User).where(User.telegram_id.in_(telegram_ids))
            )
        await engine.dispose()
