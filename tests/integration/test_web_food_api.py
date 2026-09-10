from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.integration.test_web_profile_api import auth_headers
from tests.unit.test_web_auth import BOT_TOKEN


def ingredient_payload(name: str, kcal: str = "120") -> dict[str, str | None]:
    return {
        "name": name,
        "energy_kcal_per_100g": kcal,
        "protein_g_per_100g": "5",
        "fat_g_per_100g": "3",
        "carbs_g_per_100g": "18",
        "package_weight_g": "500",
        "photo_url": "https://example.com/flour.jpg",
        "source_name": "Упаковка",
        "source_url": "https://example.com/flour",
    }


async def test_food_api_crud_pagination_dependencies_sharing_and_isolation(
    session: AsyncSession,
) -> None:
    settings = Settings(
        bot_token=BOT_TOKEN,
        bot_username="WTrackerTestBot",
        database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        _env_file=None,
    )
    app = create_web_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_session
    now = datetime.now(UTC)
    owner_headers = auth_headers(now)
    recipient_headers = auth_headers(now, telegram_id=987654321)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        await client.get("/api/v1/me", headers=recipient_headers)

        created = await client.post(
            "/api/v1/ingredients",
            headers={**owner_headers, "Idempotency-Key": "food-flour"},
            json=ingredient_payload("Мука пшеничная"),
        )
        assert created.status_code == 201
        flour = created.json()
        assert flour["nutrition_per_100g"]["energy_kcal"] == "120.00"
        assert flour["package_weight_g"] == "500.00"
        assert flour["photo_url"] == "https://example.com/flour.jpg"

        metadata_cleared = await client.patch(
            f"/api/v1/ingredients/{flour['id']}",
            headers=owner_headers,
            json={
                "package_weight_g": None,
                "photo_url": None,
                "source_name": None,
                "source_url": None,
            },
        )
        assert metadata_cleared.status_code == 200
        assert metadata_cleared.json()["package_weight_g"] is None
        assert metadata_cleared.json()["photo_url"] is None

        replay = await client.post(
            "/api/v1/ingredients",
            headers={**owner_headers, "Idempotency-Key": "food-flour"},
            json=ingredient_payload("Мука пшеничная"),
        )
        assert replay.status_code == 201
        assert replay.headers["X-Idempotent-Replayed"] == "true"

        similar = await client.post(
            "/api/v1/ingredients",
            headers={**owner_headers, "Idempotency-Key": "food-flour-copy"},
            json=ingredient_payload("мука ПШЕНИЧНАЯ "),
        )
        assert similar.status_code == 409
        assert similar.json()["error"]["code"] == "similar_food_exists"
        assert similar.json()["error"]["details"]["existing"]["id"] == flour["id"]

        searched = await client.get(
            "/api/v1/ingredients?query=МУКА",
            headers=owner_headers,
        )
        assert [item["id"] for item in searched.json()["items"]] == [flour["id"]]

        for index in range(31):
            response = await client.post(
                "/api/v1/ingredients",
                headers={
                    **owner_headers,
                    "Idempotency-Key": f"food-pagination-{index}",
                },
                json=ingredient_payload(f"Продукт {index:02d}"),
            )
            assert response.status_code == 201

        first_page = await client.get(
            "/api/v1/ingredients?sort=name_asc",
            headers=owner_headers,
        )
        assert len(first_page.json()["items"]) == 30
        assert first_page.json()["next_cursor"] is not None
        second_page = await client.get(
            "/api/v1/ingredients",
            headers=owner_headers,
            params={
                "sort": "name_asc",
                "cursor": first_page.json()["next_cursor"],
            },
        )
        first_ids = {item["id"] for item in first_page.json()["items"]}
        second_ids = {item["id"] for item in second_page.json()["items"]}
        assert len(second_ids) == 2
        assert first_ids.isdisjoint(second_ids)

        dish_created = await client.post(
            "/api/v1/dishes",
            headers={**owner_headers, "Idempotency-Key": "food-dish"},
            json={
                "name": "Тесто",
                "components": [{"ingredient_id": flour["id"], "grams": "250"}],
            },
        )
        assert dish_created.status_code == 201
        dish = dish_created.json()
        assert Decimal(dish["total_weight_g"]) == Decimal("250")
        assert Decimal(dish["nutrition_total"]["energy_kcal"]) == Decimal("300")

        updated = await client.patch(
            f"/api/v1/dishes/{dish['id']}",
            headers=owner_headers,
            json={
                "name": "Тесто для хлеба",
                "components": [{"ingredient_id": flour["id"], "grams": "300"}],
            },
        )
        assert updated.status_code == 200
        assert Decimal(updated.json()["nutrition_total"]["energy_kcal"]) == Decimal(
            "360"
        )

        consequences = await client.get(
            f"/api/v1/ingredients/{flour['id']}/delete-consequences",
            headers=owner_headers,
        )
        assert consequences.json()["can_delete"] is False
        assert consequences.json()["dependencies"] == ["Тесто для хлеба"]
        blocked = await client.delete(
            f"/api/v1/ingredients/{flour['id']}", headers=owner_headers
        )
        assert blocked.status_code == 422

        foreign = await client.get(
            f"/api/v1/dishes/{dish['id']}", headers=recipient_headers
        )
        assert foreign.status_code == 404

        package = await client.post(
            "/api/v1/sharing/packages",
            headers={**owner_headers, "Idempotency-Key": "food-share"},
            json={"type": "dishes", "item_ids": [dish["id"]]},
        )
        assert package.status_code == 201
        token = package.json()["deep_link"].split("start=")[1]

        preview = await client.get(
            f"/api/v1/sharing/packages/{token}/preview",
            headers=recipient_headers,
        )
        assert preview.status_code == 200
        assert preview.json()["type"] == "dishes"
        assert preview.json()["dishes"][0]["name"] == "Тесто для хлеба"

        imported = await client.post(
            f"/api/v1/sharing/packages/{token}/import",
            headers=recipient_headers,
            json={},
        )
        assert imported.status_code == 200
        assert imported.json()["created_ingredients"] == 1
        assert imported.json()["created_dishes"] == 1

        recipient_dishes = await client.get(
            "/api/v1/dishes?query=тесто", headers=recipient_headers
        )
        assert len(recipient_dishes.json()["items"]) == 1

        revoked = await client.delete(
            f"/api/v1/sharing/packages/{package.json()['id']}",
            headers=owner_headers,
        )
        assert revoked.status_code == 204
        unavailable = await client.get(
            f"/api/v1/sharing/packages/{token}/preview",
            headers=recipient_headers,
        )
        assert unavailable.status_code == 422
