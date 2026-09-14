from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.ingredient import Ingredient
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.unit.test_web_auth import BOT_TOKEN, sign_init_data


def auth_headers(
    auth_date: datetime,
    *,
    telegram_id: int = 279058397,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    init_data = sign_init_data(
        auth_date=auth_date,
        user={
            "id": telegram_id,
            "first_name": "Vladislav",
            "last_name": "Sakharov",
            "username": f"user_{telegram_id}",
            "language_code": "ru",
            "photo_url": "https://example.test/avatar.jpg",
        },
    )
    headers = {"Authorization": f"tma {init_data}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return headers


async def test_profile_settings_goals_reminders_and_deletion_api(
    session: AsyncSession,
) -> None:
    settings = Settings(
        bot_token=BOT_TOKEN,
        database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        app_version="0.3.0-test",
        miniapp_enabled=True,
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
        profile = await client.get("/api/v1/profile", headers=owner_headers)
        assert profile.status_code == 200
        assert profile.json()["photo_url"] == "https://example.test/avatar.jpg"
        assert profile.json()["app_version"] == "0.3.0-test"
        assert profile.json()["confirm_deletions"] is True

        settings_response = await client.patch(
            "/api/v1/profile/settings",
            headers=owner_headers,
            json={
                "timezone": "Asia/Tashkent",
                "number_format": "two_decimals",
                "after_food_add_action": "stay",
                "confirm_deletions": False,
            },
        )
        assert settings_response.status_code == 200
        assert settings_response.json()["timezone"] == "Asia/Tashkent"
        assert settings_response.json()["number_format"] == "two_decimals"
        assert settings_response.json()["confirm_deletions"] is False

        invalid_timezone = await client.patch(
            "/api/v1/profile/settings",
            headers=owner_headers,
            json={"timezone": "Not/A_Timezone"},
        )
        assert invalid_timezone.status_code == 422

        too_large_goal = await client.put(
            "/api/v1/goals/nutrition",
            headers=owner_headers,
            json={"enabled": True, "energy_kcal": "10000.01"},
        )
        assert too_large_goal.status_code == 422

        saved_goal = await client.put(
            "/api/v1/goals/nutrition",
            headers=owner_headers,
            json={
                "enabled": True,
                "energy_kcal": "2200",
                "protein_g": "140.5",
            },
        )
        assert saved_goal.status_code == 200
        assert saved_goal.json()["energy_kcal"] == "2200.00"
        assert saved_goal.json()["protein_g"] == "140.50"

        missing_key = await client.post(
            "/api/v1/reminders",
            headers=owner_headers,
            json={"type": "weigh_in", "time_local": "8:00", "weekdays": [0]},
        )
        assert missing_key.status_code == 422

        reminder = await client.post(
            "/api/v1/reminders",
            headers=auth_headers(now, idempotency_key="reminder-create-1"),
            json={
                "type": "weigh_in",
                "time_local": "8:00",
                "weekdays": [0, 2, 4],
            },
        )
        assert reminder.status_code == 201
        assert reminder.json()["time_local"] == "08:00"
        reminder_id = reminder.json()["id"]

        replay = await client.post(
            "/api/v1/reminders",
            headers=auth_headers(now, idempotency_key="reminder-create-1"),
            json={
                "type": "weigh_in",
                "time_local": "8:00",
                "weekdays": [0, 2, 4],
            },
        )
        assert replay.status_code == 201
        assert replay.headers["X-Idempotent-Replayed"] == "true"

        disabled = await client.patch(
            f"/api/v1/reminders/{reminder_id}",
            headers=owner_headers,
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        await client.get("/api/v1/profile", headers=other_headers)
        foreign_update = await client.patch(
            f"/api/v1/reminders/{reminder_id}",
            headers=other_headers,
            json={"enabled": True},
        )
        assert foreign_update.status_code == 404

        owner_profile = await client.get("/api/v1/profile", headers=owner_headers)
        owner_id = int(owner_profile.json()["id"])
        session.add(
            Ingredient(
                user_id=owner_id,
                name="Apple",
                name_normalized="apple",
                kcal_per_100g=Decimal("52"),
                protein_per_100g=Decimal("0.3"),
                fat_per_100g=Decimal("0.2"),
                carbs_per_100g=Decimal("14"),
            )
        )
        await session.flush()

        stats = await client.get("/api/v1/profile/stats", headers=owner_headers)
        assert stats.status_code == 200
        assert stats.json()["ingredients"] == 1

        exported = await client.get("/api/v1/account/export", headers=owner_headers)
        assert exported.status_code == 200
        assert exported.json()["profile"]["timezone"] == "Asia/Tashkent"
        assert exported.json()["ingredients"][0]["name"] == "Apple"

        deletion_request = await client.post(
            "/api/v1/account/deletion-request",
            headers=auth_headers(now, idempotency_key="delete-request-1"),
            json={},
        )
        assert deletion_request.status_code == 200
        challenge = deletion_request.json()

        wrong_phrase = await client.post(
            "/api/v1/account/deletion-confirm",
            headers=auth_headers(now, idempotency_key="delete-confirm-wrong"),
            json={
                "confirmation_token": challenge["confirmation_token"],
                "confirmation_phrase": "удалить",
            },
        )
        assert wrong_phrase.status_code == 422

        confirm_headers = auth_headers(now, idempotency_key="delete-confirm-1")
        deleted = await client.post(
            "/api/v1/account/deletion-confirm",
            headers=confirm_headers,
            json={
                "confirmation_token": challenge["confirmation_token"],
                "confirmation_phrase": challenge["confirmation_phrase"],
            },
        )
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted"}

        repeated = await client.post(
            "/api/v1/account/deletion-confirm",
            headers=confirm_headers,
            json={
                "confirmation_token": challenge["confirmation_token"],
                "confirmation_phrase": challenge["confirmation_phrase"],
            },
        )
        assert repeated.status_code == 200

        cleared_stats = await client.get(
            "/api/v1/profile/stats",
            headers=owner_headers,
        )
        assert cleared_stats.status_code == 200
        assert cleared_stats.json()["ingredients"] == 0
        assert cleared_stats.json()["weight_entries"] == 0
        reset_profile = await client.get("/api/v1/profile", headers=owner_headers)
        assert reset_profile.json()["timezone"] == settings.default_timezone
        assert reset_profile.json()["confirm_deletions"] is True
