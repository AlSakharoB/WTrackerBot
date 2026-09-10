from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.integration.test_web_profile_api import auth_headers
from tests.unit.test_web_auth import BOT_TOKEN


async def test_weight_api_crud_goal_ranges_and_isolation(
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
        empty = await client.get(
            "/api/v1/weight?from=2026-09-01&to=2026-09-10",
            headers=owner_headers,
        )
        assert empty.status_code == 200
        assert empty.json()["current"] is None
        assert empty.json()["points"] == []

        missing_key = await client.post(
            "/api/v1/weight",
            headers=owner_headers,
            json={"weight_kg": "82,4", "measured_at": "2026-09-10T08:00"},
        )
        assert missing_key.status_code == 422

        create_headers = {**owner_headers, "Idempotency-Key": "weight-create-1"}
        first_payload = {
            "weight_kg": "82,4",
            "measured_at": "2026-09-10T08:00",
            "note": "До завтрака",
        }
        first = await client.post(
            "/api/v1/weight",
            headers=create_headers,
            json=first_payload,
        )
        assert first.status_code == 201
        assert first.json()["measured_at"] == "2026-09-10T05:00:00Z"

        single_point = await client.get(
            "/api/v1/weight?from=2026-09-10&to=2026-09-10",
            headers=owner_headers,
        )
        assert len(single_point.json()["points"]) == 1

        replay = await client.post(
            "/api/v1/weight",
            headers=create_headers,
            json=first_payload,
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == first.json()["id"]
        assert replay.headers["X-Idempotent-Replayed"] == "true"

        second = await client.post(
            "/api/v1/weight",
            headers={**owner_headers, "Idempotency-Key": "weight-create-2"},
            json={"weight_kg": "81.75", "measured_at": "2026-09-10T20:00"},
        )
        assert second.status_code == 201
        assert second.json()["id"] != first.json()["id"]

        goal = await client.put(
            "/api/v1/goals/weight",
            headers=owner_headers,
            json={
                "enabled": True,
                "target_weight_kg": "75",
                "target_date": "2026-12-31",
            },
        )
        assert goal.status_code == 200
        assert goal.json()["start_weight_kg"] == "81.75"
        assert goal.json()["progress"]["percentage"] == "0"

        same_goal = await client.put(
            "/api/v1/goals/weight",
            headers=owner_headers,
            json={
                "enabled": True,
                "target_weight_kg": "75",
                "target_date": "2026-12-31",
            },
        )
        assert same_goal.json()["id"] == goal.json()["id"]
        fetched_goal = await client.get("/api/v1/goals/weight", headers=owner_headers)
        assert fetched_goal.status_code == 200
        assert fetched_goal.json()["id"] == goal.json()["id"]

        weight_range = await client.get(
            "/api/v1/weight?from=2026-09-10&to=2026-09-10",
            headers=owner_headers,
        )
        body = weight_range.json()
        assert weight_range.status_code == 200
        assert len(body["points"]) == 2
        assert body["current"]["id"] == second.json()["id"]
        assert body["previous"]["id"] == first.json()["id"]
        assert body["change_from_previous_kg"] == "-0.65"
        assert body["period_change_kg"] == "-0.65"
        assert [item["id"] for item in body["history"]] == [
            second.json()["id"],
            first.json()["id"],
        ]

        updated = await client.patch(
            f"/api/v1/weight/{second.json()['id']}",
            headers=owner_headers,
            json={
                "expected_updated_at": second.json()["updated_at"],
                "note": "Вечернее измерение",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["note"] == "Вечернее измерение"

        stale = await client.patch(
            f"/api/v1/weight/{first.json()['id']}",
            headers=owner_headers,
            json={
                "expected_updated_at": "2000-01-01T00:00:00Z",
                "weight_kg": "82",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "stale_data"

        await client.get("/api/v1/me", headers=other_headers)
        foreign_update = await client.patch(
            f"/api/v1/weight/{first.json()['id']}",
            headers=other_headers,
            json={
                "expected_updated_at": first.json()["updated_at"],
                "weight_kg": "70",
            },
        )
        assert foreign_update.status_code == 404
        foreign_delete = await client.delete(
            f"/api/v1/weight/{first.json()['id']}",
            headers=other_headers,
        )
        assert foreign_delete.status_code == 204

        deleted = await client.delete(
            f"/api/v1/weight/{first.json()['id']}",
            headers=owner_headers,
        )
        repeated = await client.delete(
            f"/api/v1/weight/{first.json()['id']}",
            headers=owner_headers,
        )
        assert deleted.status_code == repeated.status_code == 204

        too_long = await client.get(
            "/api/v1/weight?from=2025-09-10&to=2026-09-10",
            headers=owner_headers,
        )
        assert too_long.status_code == 422
        maximum_range = await client.get(
            "/api/v1/weight?from=2025-09-11&to=2026-09-10",
            headers=owner_headers,
        )
        assert maximum_range.status_code == 200

        disabled_goal = await client.put(
            "/api/v1/goals/weight",
            headers=owner_headers,
            json={"enabled": False},
        )
        repeated_disable = await client.put(
            "/api/v1/goals/weight",
            headers=owner_headers,
            json={"enabled": False},
        )
        assert disabled_goal.status_code == repeated_disable.status_code == 200
        assert disabled_goal.json() is None
