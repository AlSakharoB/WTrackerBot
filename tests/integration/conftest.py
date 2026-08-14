import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import create_database_engine, create_session_factory


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    engine = create_database_engine(database_url)
    connection = await engine.connect()
    transaction = await connection.begin()
    session_factory = create_session_factory(engine)
    db_session = session_factory(bind=connection)

    try:
        yield db_session
    finally:
        await db_session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()
