from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.nutrition_goal import NutritionGoal
from app.repositories.users import UserRepository
from app.utils.datetime import local_today
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.unit.test_web_auth import BOT_TOKEN, sign_init_data


async def test_ration_api_uses_snapshots_groups_meals_and_isolates_users(
    session: AsyncSession,
) -> None:
    settings = Settings(
        bot_token=BOT_TOKEN,
        database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        _env_file=None,
    )
    app = create_web_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_session
    auth_date = datetime.now(UTC)
    owner_init_data = sign_init_data(auth_date=auth_date)
    owner_headers = {"Authorization": f"tma {owner_init_data}"}
    other_init_data = sign_init_data(
        auth_date=auth_date,
        user={"id": 765432100, "first_name": "Other"},
    )
    other_headers = {"Authorization": f"tma {other_init_data}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        owner = await UserRepository(session).get_by_telegram_id(279058397)
        assert owner is not None
        today = local_today(owner.timezone)
        session.add_all(
            [
                NutritionGoal(
                    user_id=owner.id,
                    kcal_target=Decimal("100"),
                    protein_target_g=Decimal("2"),
                    fat_target_g=Decimal("2"),
                    carbs_target_g=Decimal("2"),
                    effective_from=today,
                ),
                DiaryEntry(
                    user_id=owner.id,
                    entry_date=today,
                    entry_type=DiaryEntryType.INGREDIENT,
                    ingredient_id=None,
                    dish_id=None,
                    source_name="Удалённое яблоко",
                    grams=Decimal("100"),
                    meal_type=MealType.BREAKFAST,
                    kcal_snapshot=Decimal("100"),
                    protein_snapshot=Decimal("1"),
                    fat_snapshot=Decimal("1"),
                    carbs_snapshot=Decimal("1"),
                ),
                DiaryEntry(
                    user_id=owner.id,
                    entry_date=today,
                    entry_type=DiaryEntryType.DISH,
                    ingredient_id=None,
                    dish_id=None,
                    source_name="Удалённое блюдо",
                    grams=Decimal("250.5"),
                    meal_type=MealType.LUNCH,
                    kcal_snapshot=Decimal("50"),
                    protein_snapshot=Decimal("0"),
                    fat_snapshot=Decimal("0"),
                    carbs_snapshot=Decimal("0"),
                ),
            ]
        )
        await session.flush()

        day_response = await client.get(
            f"/api/v1/ration/{today.isoformat()}",
            headers=owner_headers,
        )
        assert day_response.status_code == 200
        day = day_response.json()
        assert day["is_today"] is True
        assert day["is_future"] is False
        assert day["entry_count"] == 2
        assert day["totals"] == {
            "energy_kcal": "150.00",
            "protein_g": "1.00",
            "fat_g": "1.00",
            "carbs_g": "1.00",
        }
        assert day["macro_percentages"] == {
            "protein": 24,
            "fat": 53,
            "carbs": 23,
        }
        assert sum(day["macro_percentages"].values()) == 100
        assert [meal["type"] for meal in day["meals"]] == [
            "breakfast",
            "lunch",
            "dinner",
            "snack",
        ]
        breakfast_entry = day["meals"][0]["entries"][0]
        lunch_entry = day["meals"][1]["entries"][0]
        assert breakfast_entry["source_name"] == "Удалённое яблоко"
        assert breakfast_entry["source_available"] is False
        assert lunch_entry["type"] == "dish"
        assert lunch_entry["grams"] == "250.50"
        assert lunch_entry["source_available"] is False

        summary_response = await client.get(
            f"/api/v1/ration/{today.isoformat()}/summary",
            headers=owner_headers,
        )
        assert summary_response.status_code == 200
        assert summary_response.json()["totals"] == day["totals"]
        assert "meals" not in summary_response.json()

        yesterday = today - timedelta(days=1)
        empty_response = await client.get(
            f"/api/v1/ration/{yesterday.isoformat()}",
            headers=owner_headers,
        )
        empty_day = empty_response.json()
        assert empty_day["entry_count"] == 0
        assert empty_day["goal"] is None
        assert empty_day["macro_percentages"] == {
            "protein": 0,
            "fat": 0,
            "carbs": 0,
        }

        await client.get("/api/v1/me", headers=other_headers)
        foreign_response = await client.get(
            f"/api/v1/ration/{today.isoformat()}",
            headers=other_headers,
        )
        assert foreign_response.status_code == 200
        assert foreign_response.json()["entry_count"] == 0

        tomorrow = today + timedelta(days=1)
        future_response = await client.get(
            f"/api/v1/ration/{tomorrow.isoformat()}",
            headers=owner_headers,
        )
        assert future_response.status_code == 200
        assert future_response.json()["is_future"] is True

        invalid_date = await client.get(
            "/api/v1/ration/03.09.2026",
            headers=owner_headers,
        )
        assert invalid_date.status_code == 422
