from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.open_food_facts import ExternalFetch
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.integration.test_web_profile_api import auth_headers
from tests.unit.test_web_auth import BOT_TOKEN


class FakeOpenFoodFactsClient:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, barcode: str) -> ExternalFetch:
        self.calls += 1
        if barcode == "96385074":
            return ExternalFetch(200, {"status": 0})
        return ExternalFetch(
            200,
            {
                "status": 1,
                "product": {
                    "code": barcode,
                    "product_name": "Тестовый батончик",
                    "brands": "Test Brand",
                    "quantity": "50 g",
                    "product_quantity": 50,
                    "product_quantity_unit": "g",
                    "nutriments": {
                        "energy-kcal_100g": 400,
                        "proteins_100g": 20,
                        "fat_100g": 10,
                        "carbohydrates_100g": 50,
                    },
                    "image_front_url": (
                        "https://images.openfoodfacts.org/images/products/test.jpg"
                    ),
                    "last_modified_t": 1_788_966_000,
                },
            },
        )

    async def aclose(self) -> None:
        return None


async def test_barcode_lookup_cache_confirmation_creation_and_duplicate(
    session: AsyncSession,
) -> None:
    settings = Settings(
        bot_token=BOT_TOKEN,
        database_url="postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        barcode_rate_limit_count=100,
        _env_file=None,
    )
    app = create_web_app(settings)
    await app.state.open_food_facts_client.aclose()
    fake_client = FakeOpenFoodFactsClient()
    app.state.open_food_facts_client = fake_client

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_session
    owner_headers = auth_headers(datetime.now(UTC), telegram_id=700800900)
    other_headers = auth_headers(datetime.now(UTC), telegram_id=700800901)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        await client.get("/api/v1/me", headers=owner_headers)
        await client.get("/api/v1/me", headers=other_headers)
        first = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "4006 381333931"},
        )
        second = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "4006381333931"},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert fake_client.calls == 1
        lookup = second.json()
        assert lookup["found"] is True
        assert lookup["package_weight_g"] == "50.00"
        assert lookup["nutrition_per_100g"]["energy_kcal"] == "400.00"
        assert lookup["missing_fields"] == []

        not_found_first = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "96385074"},
        )
        not_found_second = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "96385074"},
        )
        assert not_found_first.status_code == 200
        assert not_found_second.json()["found"] is False
        assert fake_client.calls == 2

        create_payload = {
            "confirmation_token": lookup["confirmation_token"],
            "confirmed": True,
            "name": lookup["name"],
            "energy_kcal_per_100g": lookup["nutrition_per_100g"]["energy_kcal"],
            "protein_g_per_100g": lookup["nutrition_per_100g"]["protein_g"],
            "fat_g_per_100g": lookup["nutrition_per_100g"]["fat_g"],
            "carbs_g_per_100g": lookup["nutrition_per_100g"]["carbs_g"],
            "package_weight_g": lookup["package_weight_g"],
            "photo_url": lookup["photo_url"],
        }
        created = await client.post(
            "/api/v1/barcodes/4006381333931/create-ingredient",
            headers={**owner_headers, "Idempotency-Key": "barcode-create"},
            json=create_payload,
        )
        assert created.status_code == 201
        assert created.json()["source_name"] == "Open Food Facts"
        assert created.json()["source_url"].endswith("/product/4006381333931")
        replay = await client.post(
            "/api/v1/barcodes/4006381333931/create-ingredient",
            headers={**owner_headers, "Idempotency-Key": "barcode-create"},
            json=create_payload,
        )
        assert replay.status_code == 201
        assert replay.headers["X-Idempotent-Replayed"] == "true"
        duplicate = await client.post(
            "/api/v1/barcodes/4006381333931/create-ingredient",
            headers={**owner_headers, "Idempotency-Key": "barcode-create-again"},
            json=create_payload,
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "barcode_already_imported"

        similar_lookup = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "036000291452"},
        )
        similar_payload = {
            **create_payload,
            "confirmation_token": similar_lookup.json()["confirmation_token"],
        }
        similar = await client.post(
            "/api/v1/barcodes/036000291452/create-ingredient",
            headers={**owner_headers, "Idempotency-Key": "barcode-similar-name"},
            json=similar_payload,
        )
        assert similar.status_code == 409
        assert similar.json()["error"]["code"] == "similar_food_exists"

        wrong_user = await client.post(
            "/api/v1/barcodes/4006381333931/create-ingredient",
            headers={**other_headers, "Idempotency-Key": "barcode-wrong-user"},
            json=create_payload,
        )
        assert wrong_user.status_code == 422

        invalid = await client.post(
            "/api/v1/barcodes/lookup",
            headers=owner_headers,
            json={"barcode": "4006381333932"},
        )
        assert invalid.status_code == 422
