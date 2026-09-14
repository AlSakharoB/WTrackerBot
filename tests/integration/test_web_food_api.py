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
        miniapp_enabled=True,
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


async def test_food_folder_api_organizes_catalog_without_deleting_food(
    session: AsyncSession,
) -> None:
    settings = Settings(
        bot_token=BOT_TOKEN,
        database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        miniapp_enabled=True,
        _env_file=None,
    )
    app = create_web_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_session
    now = datetime.now(UTC)
    owner_headers = auth_headers(now, telegram_id=111222333)
    other_headers = auth_headers(now, telegram_id=444555666)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        await client.get("/api/v1/me", headers=other_headers)
        ingredient = (
            await client.post(
                "/api/v1/ingredients",
                headers={**owner_headers, "Idempotency-Key": "folder-owner-food"},
                json=ingredient_payload("M8 owner ingredient"),
            )
        ).json()
        foreign_ingredient = (
            await client.post(
                "/api/v1/ingredients",
                headers={**other_headers, "Idempotency-Key": "folder-foreign-food"},
                json=ingredient_payload("M8 foreign ingredient"),
            )
        ).json()
        dish = (
            await client.post(
                "/api/v1/dishes",
                headers={**owner_headers, "Idempotency-Key": "folder-owner-dish"},
                json={
                    "name": "M8 owner dish",
                    "components": [{"ingredient_id": ingredient["id"], "grams": "100"}],
                },
            )
        ).json()

        first = await client.post(
            "/api/v1/food-folders",
            headers={**owner_headers, "Idempotency-Key": "folder-milk"},
            json={"name": "Ｍｉｌｋ"},
        )
        second = await client.post(
            "/api/v1/food-folders",
            headers={**owner_headers, "Idempotency-Key": "folder-fruit"},
            json={"name": "Fruit"},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        milk = first.json()
        fruit = second.json()
        assert [milk["sort_order"], fruit["sort_order"]] == [0, 1]

        duplicate = await client.post(
            "/api/v1/food-folders",
            headers={**owner_headers, "Idempotency-Key": "folder-duplicate"},
            json={"name": " milk! "},
        )
        assert duplicate.status_code == 409
        same_name_other_user = await client.post(
            "/api/v1/food-folders",
            headers={**other_headers, "Idempotency-Key": "folder-other-milk"},
            json={"name": "milk"},
        )
        assert same_name_other_user.status_code == 201

        atomic_failure = await client.post(
            "/api/v1/food-items/folder-batch",
            headers=owner_headers,
            json={
                "type": "ingredient",
                "item_ids": [ingredient["id"], foreign_ingredient["id"]],
                "folder_id": milk["id"],
            },
        )
        assert atomic_failure.status_code == 404
        unchanged = await client.get(
            f"/api/v1/ingredients/{ingredient['id']}", headers=owner_headers
        )
        assert unchanged.json()["folder_id"] is None

        moved_ingredient = await client.put(
            f"/api/v1/food-items/ingredient/{ingredient['id']}/folder",
            headers=owner_headers,
            json={"folder_id": milk["id"]},
        )
        assert moved_ingredient.status_code == 200
        moved_dish = await client.put(
            f"/api/v1/food-items/dish/{dish['id']}/folder",
            headers=owner_headers,
            json={"folder_id": milk["id"]},
        )
        assert moved_dish.status_code == 200

        folder_list = await client.get("/api/v1/food-folders", headers=owner_headers)
        assert folder_list.json()["items"][0]["item_count"] == 2
        filtered = await client.get(
            "/api/v1/ingredients",
            headers=owner_headers,
            params={"folder_id": milk["id"]},
        )
        assert [item["id"] for item in filtered.json()["items"]] == [ingredient["id"]]
        assert filtered.json()["items"][0]["folder_id"] == milk["id"]

        for target in (fruit["id"], milk["id"]):
            response = await client.put(
                f"/api/v1/food-items/ingredient/{ingredient['id']}/folder",
                headers=owner_headers,
                json={"folder_id": target},
            )
            assert response.status_code == 200
        assert (
            await client.get(
                f"/api/v1/ingredients/{ingredient['id']}", headers=owner_headers
            )
        ).json()["folder_id"] == milk["id"]

        reordered = await client.post(
            "/api/v1/food-folders/reorder",
            headers=owner_headers,
            json={"folder_ids": [fruit["id"], milk["id"]]},
        )
        assert [item["id"] for item in reordered.json()["items"]] == [
            fruit["id"],
            milk["id"],
        ]
        invalid_reorder = await client.post(
            "/api/v1/food-folders/reorder",
            headers=owner_headers,
            json={"folder_ids": [milk["id"]]},
        )
        assert invalid_reorder.status_code == 422

        foreign_delete = await client.delete(
            f"/api/v1/food-folders/{milk['id']}", headers=other_headers
        )
        assert foreign_delete.status_code == 404
        deleted = await client.delete(
            f"/api/v1/food-folders/{milk['id']}", headers=owner_headers
        )
        assert deleted.status_code == 204
        unfiled_ingredients = await client.get(
            "/api/v1/ingredients?folder_id=unfiled", headers=owner_headers
        )
        unfiled_dishes = await client.get(
            "/api/v1/dishes?folder_id=unfiled", headers=owner_headers
        )
        assert ingredient["id"] in {
            item["id"] for item in unfiled_ingredients.json()["items"]
        }
        assert dish["id"] in {item["id"] for item in unfiled_dishes.json()["items"]}
        remaining = await client.get("/api/v1/food-folders", headers=owner_headers)
        assert [
            (item["id"], item["sort_order"]) for item in remaining.json()["items"]
        ] == [(fruit["id"], 0)]
