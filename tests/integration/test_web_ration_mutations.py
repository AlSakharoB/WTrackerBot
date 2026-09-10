from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.ingredient import Ingredient
from app.repositories.users import UserRepository
from app.utils.datetime import local_today
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.integration.test_web_profile_api import auth_headers
from tests.unit.test_web_auth import BOT_TOKEN


async def test_ration_entry_management_and_source_search(
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
    now = datetime.now(UTC)
    owner_headers = auth_headers(now)
    other_headers = auth_headers(now, telegram_id=987654321)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        owner = await UserRepository(session).get_by_telegram_id(279058397)
        assert owner is not None
        today = local_today(owner.timezone)
        ingredient = Ingredient(
            user_id=owner.id,
            name="Яблоко Голден",
            name_normalized="яблоко голден",
            kcal_per_100g=Decimal("52"),
            protein_per_100g=Decimal("0.3"),
            fat_per_100g=Decimal("0.2"),
            carbs_per_100g=Decimal("14"),
        )
        session.add(ingredient)
        await session.flush()

        sources = await client.get(
            "/api/v1/ration/sources?q=ЯБЛОКО&kind=ingredient",
            headers=owner_headers,
        )
        assert sources.status_code == 200
        assert sources.json()["items"] == [
            {
                "id": str(ingredient.id),
                "type": "ingredient",
                "name": "Яблоко Голден",
                "default_grams": "100",
                "nutrition_per_100g": {
                    "energy_kcal": "52",
                    "protein_g": "0.3",
                    "fat_g": "0.2",
                    "carbs_g": "14",
                },
                "usage_count": 0,
                "last_used_at": None,
            }
        ]

        create_headers = {
            **owner_headers,
            "Idempotency-Key": "ration-create-1",
        }
        payload = {
            "source_type": "ingredient",
            "source_id": str(ingredient.id),
            "grams": "125,5",
            "meal_type": "breakfast",
        }
        created = await client.post(
            f"/api/v1/ration/{today.isoformat()}/entries",
            headers=create_headers,
            json=payload,
        )
        assert created.status_code == 201
        assert created.json()["grams"] == "125.50"
        assert created.json()["nutrition"]["energy_kcal"] == "65.26"
        entry_id = created.json()["id"]

        replay = await client.post(
            f"/api/v1/ration/{today.isoformat()}/entries",
            headers=create_headers,
            json=payload,
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == entry_id
        assert replay.headers["X-Idempotent-Replayed"] == "true"

        conflict = await client.post(
            f"/api/v1/ration/{today.isoformat()}/entries",
            headers=create_headers,
            json={**payload, "grams": "126"},
        )
        assert conflict.status_code == 409

        too_large = await client.post(
            f"/api/v1/ration/{today.isoformat()}/entries",
            headers={**owner_headers, "Idempotency-Key": "ration-create-2"},
            json={**payload, "grams": "1000001"},
        )
        assert too_large.status_code == 422

        stale = await client.patch(
            f"/api/v1/ration/entries/{entry_id}",
            headers=owner_headers,
            json={
                "expected_updated_at": "2000-01-01T00:00:00Z",
                "grams": "130.5",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "stale_data"

        await client.get("/api/v1/me", headers=other_headers)
        foreign = await client.patch(
            f"/api/v1/ration/entries/{entry_id}",
            headers=other_headers,
            json={
                "expected_updated_at": created.json()["updated_at"],
                "meal_type": "lunch",
            },
        )
        assert foreign.status_code == 404

        await session.execute(delete(Ingredient).where(Ingredient.id == ingredient.id))
        await session.flush()
        session.expire_all()

        unavailable = await client.patch(
            f"/api/v1/ration/entries/{entry_id}",
            headers=owner_headers,
            json={
                "expected_updated_at": created.json()["updated_at"],
                "grams": "130.5",
            },
        )
        assert unavailable.status_code == 422

        tomorrow = today + timedelta(days=1)
        moved = await client.patch(
            f"/api/v1/ration/entries/{entry_id}",
            headers=owner_headers,
            json={
                "expected_updated_at": created.json()["updated_at"],
                "meal_type": "lunch",
                "entry_date": tomorrow.isoformat(),
            },
        )
        assert moved.status_code == 200
        assert moved.json()["meal_type"] == "lunch"
        assert moved.json()["source_available"] is False

        copied = await client.post(
            f"/api/v1/ration/entries/{entry_id}/copy",
            headers={**owner_headers, "Idempotency-Key": "ration-copy-1"},
            json={"entry_date": today.isoformat(), "meal_type": "dinner"},
        )
        assert copied.status_code == 201
        assert copied.json()["source_available"] is False
        assert copied.json()["nutrition"] == created.json()["nutrition"]

        copied_replay = await client.post(
            f"/api/v1/ration/entries/{entry_id}/copy",
            headers={**owner_headers, "Idempotency-Key": "ration-copy-1"},
            json={"entry_date": today.isoformat(), "meal_type": "dinner"},
        )
        assert copied_replay.json()["id"] == copied.json()["id"]
        assert copied_replay.headers["X-Idempotent-Replayed"] == "true"

        foreign_delete = await client.delete(
            f"/api/v1/ration/entries/{entry_id}",
            headers=other_headers,
        )
        assert foreign_delete.status_code == 204
        still_present = await client.get(
            f"/api/v1/ration/{tomorrow.isoformat()}",
            headers=owner_headers,
        )
        assert still_present.json()["entry_count"] == 1

        deleted = await client.delete(
            f"/api/v1/ration/entries/{entry_id}",
            headers=owner_headers,
        )
        repeated_delete = await client.delete(
            f"/api/v1/ration/entries/{entry_id}",
            headers=owner_headers,
        )
        assert deleted.status_code == repeated_delete.status_code == 204
