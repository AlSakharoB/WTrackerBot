from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.repositories.users import UserRepository
from app.utils.datetime import local_today
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.unit.test_web_auth import BOT_TOKEN, sign_init_data


async def test_ration_week_snapshots_boundaries_and_user_isolation(
    session: AsyncSession,
) -> None:
    app = create_web_app(
        Settings(
            bot_token=BOT_TOKEN,
            database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
            miniapp_enabled=True,
            _env_file=None,
        )
    )

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_session
    owner_headers = {
        "Authorization": f"tma {sign_init_data(auth_date=datetime.now(UTC))}"
    }
    other_init_data = sign_init_data(
        auth_date=datetime.now(UTC),
        user={"id": 765432100, "first_name": "Other"},
    )
    other_headers = {"Authorization": f"tma {other_init_data}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        owner = await UserRepository(session).get_by_telegram_id(279058397)
        assert owner is not None
        owner.timezone = "Pacific/Kiritimati"
        start = date(2025, 12, 29)
        for entry_date, kcal in [
            (start - timedelta(days=1), "999"),
            (start, "40.25"),
            (start, "59.50"),
            (start + timedelta(days=6), "75"),
            (start + timedelta(days=7), "999"),
        ]:
            session.add(
                DiaryEntry(
                    user_id=owner.id,
                    entry_date=entry_date,
                    entry_type=DiaryEntryType.INGREDIENT,
                    source_name="Deleted source",
                    grams=Decimal("100"),
                    meal_type=MealType.BREAKFAST,
                    kcal_snapshot=Decimal(kcal),
                    protein_snapshot=Decimal("0"),
                    fat_snapshot=Decimal("0"),
                    carbs_snapshot=Decimal("0"),
                )
            )
        await session.flush()
        response = await client.get(
            "/api/v1/ration/week?week_start=2026-01-01", headers=owner_headers
        )
        assert response.status_code == 200
        week = response.json()
        assert week["week_start"] == "2025-12-29"
        assert week["week_end"] == "2026-01-04"
        assert week["today"] == local_today(owner.timezone).isoformat()
        assert week["timezone"] == owner.timezone
        assert len(week["days"]) == 7
        assert week["days"][0] == {
            "date": "2025-12-29",
            "entry_count": 2,
            "energy_kcal": "99.75",
        }
        assert week["days"][1] == {
            "date": "2025-12-30",
            "entry_count": 0,
            "energy_kcal": "0",
        }
        assert week["days"][-1] == {
            "date": "2026-01-04",
            "entry_count": 1,
            "energy_kcal": "75.00",
        }

        foreign = await client.get(
            "/api/v1/ration/week?week_start=2026-01-01", headers=other_headers
        )
        assert foreign.status_code == 200
        assert all(day["entry_count"] == 0 for day in foreign.json()["days"])
        for query in ["", "?week_start=no-date", "?week_start=9999-12-31"]:
            invalid = await client.get(
                f"/api/v1/ration/week{query}", headers=owner_headers
            )
            assert invalid.status_code == 422
        earliest = await client.get(
            "/api/v1/ration/week?week_start=0001-01-01", headers=owner_headers
        )
        assert earliest.status_code == 200
        latest = await client.get(
            "/api/v1/ration/week?week_start=9999-12-25", headers=owner_headers
        )
        assert latest.status_code == 200
