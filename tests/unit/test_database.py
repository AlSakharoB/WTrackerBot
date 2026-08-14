from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import create_database_engine, create_session_factory


async def test_session_factory_uses_async_sessions() -> None:
    engine = create_database_engine(
        "postgresql+asyncpg://postgres:postgres@localhost/nutrition_bot"
    )

    try:
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            assert isinstance(session, AsyncSession)
            assert session.sync_session.expire_on_commit is False
    finally:
        await engine.dispose()
