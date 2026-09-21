import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from app.barcodes import normalize_gtin, safe_off_image_url
from app.exceptions import ValidationError
from app.integrations.open_food_facts import (
    ExternalProductInvalidResponse,
    ExternalProductRateLimited,
    ExternalProductUnavailable,
    OpenFoodFactsClient,
    parse_open_food_facts,
)
from app.services.barcodes import BarcodeConfirmationSigner, BarcodeRateLimiter


@pytest.mark.parametrize(
    "barcode",
    ["96385074", "036000291452", "4006381333931", "10012345000017"],
)
def test_normalize_gtin_accepts_supported_lengths_and_spaces(barcode: str) -> None:
    spaced = f" {barcode[:4]} {barcode[4:]}\n"
    assert normalize_gtin(spaced) == barcode


@pytest.mark.parametrize(
    "barcode",
    [
        "96385075",
        "036000291453",
        "4006381333932",
        "10012345000018",
        "1234567",
        "400638133393A",
        "400-6381333931",
        "１２３４５６７０",
    ],
)
def test_normalize_gtin_rejects_invalid_codes(barcode: str) -> None:
    with pytest.raises(ValidationError):
        normalize_gtin(barcode)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://images.openfoodfacts.org/images/products/a.jpg", True),
        ("https://static.openfoodfacts.org/images/a.jpg", True),
        ("http://images.openfoodfacts.org/a.jpg", False),
        ("https://images.openfoodfacts.org.evil.test/a.jpg", False),
        ("https://user@images.openfoodfacts.org/a.jpg", False),
        ("https://images.openfoodfacts.org:invalid/a.jpg", False),
        ("https://127.0.0.1/a.jpg", False),
    ],
)
def test_off_image_allowlist_blocks_ssrf_urls(url: str, allowed: bool) -> None:
    assert (safe_off_image_url(url) is not None) is allowed


def test_parser_uses_per_100g_values_and_structured_weight() -> None:
    result = parse_open_food_facts(
        {
            "status": 1,
            "product": {
                "product_name": " Test  product ",
                "brands": "Brand",
                "quantity": "0,4 kg",
                "product_quantity": "0,4",
                "product_quantity_unit": "kg",
                "serving_size": "30 g",
                "image_front_url": "https://images.openfoodfacts.org/a.jpg",
                "nutriments": {
                    "energy-kcal_100g": "123,4",
                    "proteins_100g": 4.5,
                    "fat_100g": "2.1",
                    "carbohydrates_100g": 18,
                    "energy-kcal_serving": 999,
                },
            },
        },
        "4006381333931",
    )
    assert result.found
    assert result.name == "Test product"
    assert result.package_weight_g == Decimal("400.0")
    assert result.nutrition_per_100g.energy_kcal == Decimal("123.4")
    assert result.missing_fields == ()


def test_parser_derives_kcal_from_kj_but_ignores_serving_only_values() -> None:
    result = parse_open_food_facts(
        {
            "status": 1,
            "product": {
                "product_name": "Drink",
                "product_quantity": 500,
                "product_quantity_unit": "ml",
                "nutriments": {
                    "energy-kj_100g": "418.4",
                    "proteins_serving": 3,
                    "fat_serving": 2,
                    "carbohydrates_serving": 9,
                },
            },
        },
        "4006381333931",
    )
    assert result.nutrition_per_100g.energy_kcal == Decimal("100")
    assert result.package_weight_g is None
    assert result.derived_fields == ("energy_kcal",)
    assert {"protein_g", "fat_g", "carbs_g", "photo_url"}.issubset(
        result.missing_fields
    )


def test_parser_preserves_all_missing_values_as_missing() -> None:
    result = parse_open_food_facts(
        {"status": 1, "product": {"nutriments": {}}},
        "4006381333931",
    )

    assert result.found
    assert result.name is None
    assert result.package_weight_g is None
    assert result.nutrition_per_100g.energy_kcal is None
    assert result.nutrition_per_100g.protein_g is None
    assert result.nutrition_per_100g.fat_g is None
    assert result.nutrition_per_100g.carbs_g is None
    assert set(result.missing_fields) == {
        "name",
        "package_weight_g",
        "energy_kcal",
        "protein_g",
        "fat_g",
        "carbs_g",
        "photo_url",
    }


def test_parser_accepts_v3_success_and_missing_responses() -> None:
    found = parse_open_food_facts(
        {
            "status": "success",
            "product": {
                "product_name": "Test",
                "nutriments": {"energy-kcal_100g": 100},
            },
        },
        "4006381333931",
    )
    missing = parse_open_food_facts(
        {"status": "failure", "errors": [{"id": "product_not_found"}]},
        "036000291452",
    )

    assert found.found
    assert found.name == "Test"
    assert not missing.found


def _client(
    handler: httpx.AsyncBaseTransport | httpx.MockTransport,
    *,
    retries: int = 0,
    max_bytes: int = 1024,
) -> OpenFoodFactsClient:
    return OpenFoodFactsClient(
        base_url="https://world.openfoodfacts.org",
        user_agent="WTrackerBot/test (test@example.com)",
        timeout_seconds=1,
        retries=retries,
        concurrency=2,
        max_response_bytes=max_bytes,
        circuit_failures=2,
        circuit_cooldown_seconds=10,
        transport=handler,
    )


async def test_off_client_requests_only_fixed_product_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/product/4006381333931"
        assert "fields" in request.url.params
        assert request.url.params["product_type"] == "all"
        assert request.headers["user-agent"].startswith("WTrackerBot/test")
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"status": 0},
        )

    client = _client(httpx.MockTransport(handler))
    try:
        result = await client.fetch("4006381333931")
        assert result.response_json == {"status": 0}
    finally:
        await client.aclose()


async def test_off_client_follows_only_trusted_product_redirects() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": (
                        "https://world.openproductsfacts.org/api/v3/product/"
                        "4006381333931"
                    )
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"status": "success", "product": {"product_name": "Test"}},
        )

    client = _client(httpx.MockTransport(handler))
    try:
        result = await client.fetch("4006381333931")
    finally:
        await client.aclose()

    assert result.response_json["status"] == "success"
    assert len(requests) == 2
    assert requests[1].url.host == "world.openproductsfacts.org"
    assert requests[1].url.params["product_type"] == "all"


async def test_off_client_rejects_untrusted_product_redirect() -> None:
    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                302,
                headers={"location": "https://evil.example/product"},
            )
        )
    )
    try:
        with pytest.raises(ExternalProductInvalidResponse, match="небезопасное"):
            await client.fetch("4006381333931")
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("status", "content_type", "content", "error_type"),
    [
        (429, "application/json", b"{}", ExternalProductRateLimited),
        (500, "application/json", b"{}", ExternalProductUnavailable),
        (200, "text/html", b"{}", ExternalProductInvalidResponse),
        (200, "application/json", b"{broken", ExternalProductInvalidResponse),
        (200, "application/json", b"{}" * 600, ExternalProductInvalidResponse),
    ],
)
async def test_off_client_rejects_external_failures(
    status: int,
    content_type: str,
    content: bytes,
    error_type: type[Exception],
) -> None:
    client = _client(
        httpx.MockTransport(
            lambda request: httpx.Response(
                status,
                headers={"content-type": content_type},
                content=content,
            )
        )
    )
    try:
        with pytest.raises(error_type):
            await client.fetch("4006381333931")
    finally:
        await client.aclose()


async def test_off_client_retries_temporary_error_and_coalesces_equal_requests() -> (
    None
):
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        if calls == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"status": 0})

    client = _client(httpx.MockTransport(handler), retries=1)
    try:
        results = await asyncio.gather(
            client.fetch("4006381333931"),
            client.fetch("4006381333931"),
        )
        assert results[0] == results[1]
        assert calls == 2
    finally:
        await client.aclose()


async def test_off_client_maps_timeout_to_temporary_unavailability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(ExternalProductUnavailable):
            await client.fetch("4006381333931")
    finally:
        await client.aclose()


async def test_off_client_retries_network_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("dns failure", request=request)
        return httpx.Response(200, json={"status": 0})

    client = _client(httpx.MockTransport(handler), retries=1)
    try:
        result = await client.fetch("4006381333931")
    finally:
        await client.aclose()

    assert result.response_json == {"status": 0}
    assert calls == 2


async def test_off_client_opens_circuit_after_repeated_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={})

    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(ExternalProductUnavailable):
            await client.fetch("4006381333931")
        with pytest.raises(ExternalProductUnavailable):
            await client.fetch("036000291452")
        with pytest.raises(ExternalProductUnavailable):
            await client.fetch("96385074")
        assert calls == 2
    finally:
        await client.aclose()


def test_confirmation_is_bound_to_user_barcode_and_time() -> None:
    signer = BarcodeConfirmationSigner("secret", 60)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    token = signer.issue(10, "4006381333931", now=now)
    signer.verify(token, 10, "4006381333931", now=now + timedelta(seconds=60))
    with pytest.raises(ValidationError):
        signer.verify(token, 11, "4006381333931", now=now)
    with pytest.raises(ValidationError):
        signer.verify(token, 10, "4006381333931", now=now + timedelta(seconds=61))
    with pytest.raises(ValidationError):
        signer.verify("not.a-valid-token", 10, "4006381333931", now=now)


async def test_barcode_rate_limiter_is_per_user() -> None:
    limiter = BarcodeRateLimiter(1, 60)
    assert (await limiter.check(1)).allowed
    assert not (await limiter.check(1)).allowed
    assert (await limiter.check(2)).allowed
