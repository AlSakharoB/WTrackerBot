import asyncio
import os

import pytest
from sqlalchemy import text

from app.db.session import create_database_engine


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
