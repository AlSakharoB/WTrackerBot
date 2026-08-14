import asyncio
from contextlib import suppress

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def test_cancelled_transaction_does_not_leave_partial_data(
    session: AsyncSession,
) -> None:
    telegram_id = 9920000001
    flushed = asyncio.Event()

    async def interrupted_operation() -> None:
        async with session.begin_nested():
            session.add(
                User(
                    telegram_id=telegram_id,
                    first_name="Interrupted",
                    timezone="Europe/Moscow",
                )
            )
            await session.flush()
            flushed.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(interrupted_operation())
    await flushed.wait()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task

    remaining = await session.scalar(
        select(func.count(User.id)).where(User.telegram_id == telegram_id)
    )
    assert remaining == 0
