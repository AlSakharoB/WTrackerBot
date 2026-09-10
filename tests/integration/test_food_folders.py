import asyncio
import os
import secrets
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select

from app.db.models.food_folder import FoodFolderItem
from app.db.models.ingredient import Ingredient
from app.db.models.user import User
from app.db.session import create_database_engine, create_session_factory
from app.repositories.food_folders import FoodFolderRepository
from app.services.food_folders import FoodFolderService


async def test_concurrent_moves_keep_one_folder_assignment() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    user_id: int | None = None
    try:
        async with session_factory() as session, session.begin():
            user = User(telegram_id=secrets.randbelow(8_000_000_000) + 1_000_000_000)
            session.add(user)
            await session.flush()
            user_id = user.id
            ingredient = Ingredient(
                user_id=user.id,
                name="Concurrent folder item",
                name_normalized="concurrent folder item",
                kcal_per_100g=Decimal("100"),
                protein_per_100g=Decimal("1"),
                fat_per_100g=Decimal("1"),
                carbs_per_100g=Decimal("1"),
            )
            session.add(ingredient)
            await session.flush()
            service = FoodFolderService(FoodFolderRepository(session))
            first = await service.create(user.id, "First")
            second = await service.create(user.id, "Second")
            ingredient_id = ingredient.id
            folder_ids = {first.id, second.id}

        async def move(folder_id: int) -> None:
            async with session_factory() as session, session.begin():
                await FoodFolderService(FoodFolderRepository(session)).move(
                    user_id,
                    item_type="ingredient",
                    item_ids=[ingredient_id],
                    folder_id=folder_id,
                )

        await asyncio.gather(*(move(folder_id) for folder_id in folder_ids))

        async with session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        func.count(FoodFolderItem.id),
                        func.min(FoodFolderItem.folder_id),
                    ).where(FoodFolderItem.ingredient_id == ingredient_id)
                )
            ).one()
            assert rows[0] == 1
            assert rows[1] in folder_ids
    finally:
        if user_id is not None:
            async with session_factory() as session, session.begin():
                await session.execute(delete(User).where(User.id == user_id))
        await engine.dispose()
