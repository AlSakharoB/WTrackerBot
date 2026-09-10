from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Any

import httpx

from app.barcodes import decimal_value, safe_off_image_url

logger = logging.getLogger(__name__)
PROVIDER = "open_food_facts"
REQUEST_FIELDS = ",".join(
    (
        "code",
        "product_name",
        "brands",
        "quantity",
        "product_quantity",
        "product_quantity_unit",
        "serving_size",
        "nutriments",
        "image_front_url",
        "image_front_small_url",
        "last_modified_t",
    )
)


class ExternalProductError(Exception):
    pass


class ExternalProductRateLimited(ExternalProductError):
    pass


class ExternalProductUnavailable(ExternalProductError):
    pass


class ExternalProductInvalidResponse(ExternalProductError):
    pass


@dataclass(frozen=True, slots=True)
class ProductNutrition:
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbs_g: Decimal | None


@dataclass(frozen=True, slots=True)
class ExternalProduct:
    barcode: str
    found: bool
    name: str | None
    brand: str | None
    package_weight_g: Decimal | None
    package_quantity: str | None
    package_quantity_unit: str | None
    serving_size: str | None
    nutrition_per_100g: ProductNutrition
    photo_url: str | None
    missing_fields: tuple[str, ...]
    derived_fields: tuple[str, ...]
    source: str = PROVIDER


@dataclass(frozen=True, slots=True)
class ExternalFetch:
    http_status: int
    response_json: dict[str, object]


def _clean_text(value: object, limit: int = 255) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] or None


def _limited_decimal(value: object, maximum: Decimal) -> Decimal | None:
    result = decimal_value(value)
    return result if result is not None and result <= maximum else None


def _package_weight(product: dict[str, object]) -> tuple[Decimal | None, str | None]:
    quantity = decimal_value(product.get("product_quantity"))
    unit = _clean_text(product.get("product_quantity_unit"), 16)
    if quantity is None or unit is None:
        return None, unit
    normalized_unit = unit.lower()
    multipliers = {
        "g": Decimal("1"),
        "gram": Decimal("1"),
        "grams": Decimal("1"),
        "kg": Decimal("1000"),
        "kilogram": Decimal("1000"),
        "kilograms": Decimal("1000"),
        "mg": Decimal("0.001"),
    }
    multiplier = multipliers.get(normalized_unit)
    if multiplier is None:
        return None, unit
    grams = quantity * multiplier
    if grams < Decimal("0.01") or grams > Decimal("1000000"):
        return None, unit
    return grams, unit


def parse_open_food_facts(payload: dict[str, object], barcode: str) -> ExternalProduct:
    if payload.get("status") in {0, "0"} or not isinstance(
        payload.get("product"), dict
    ):
        return ExternalProduct(
            barcode=barcode,
            found=False,
            name=None,
            brand=None,
            package_weight_g=None,
            package_quantity=None,
            package_quantity_unit=None,
            serving_size=None,
            nutrition_per_100g=ProductNutrition(None, None, None, None),
            photo_url=None,
            missing_fields=("product",),
            derived_fields=(),
        )

    product: dict[str, object] = payload["product"]  # type: ignore[assignment]
    nutriments = product.get("nutriments")
    nutrients: dict[str, object] = nutriments if isinstance(nutriments, dict) else {}
    derived: list[str] = []
    energy = _limited_decimal(nutrients.get("energy-kcal_100g"), Decimal("1500"))
    if energy is None:
        energy_kj_raw = nutrients.get("energy-kj_100g")
        if energy_kj_raw is None:
            energy_kj_raw = nutrients.get("energy_100g")
        energy_kj = _limited_decimal(
            energy_kj_raw,
            Decimal("6276"),
        )
        if energy_kj is not None:
            energy = energy_kj / Decimal("4.184")
            derived.append("energy_kcal")
    nutrition = ProductNutrition(
        energy_kcal=energy,
        protein_g=_limited_decimal(nutrients.get("proteins_100g"), Decimal("100")),
        fat_g=_limited_decimal(nutrients.get("fat_100g"), Decimal("100")),
        carbs_g=_limited_decimal(nutrients.get("carbohydrates_100g"), Decimal("100")),
    )
    package_weight, package_unit = _package_weight(product)
    name = _clean_text(product.get("product_name"))
    photo = safe_off_image_url(
        product.get("image_front_url") or product.get("image_front_small_url")
    )
    missing = []
    for field, value in (
        ("name", name),
        ("package_weight_g", package_weight),
        ("energy_kcal", nutrition.energy_kcal),
        ("protein_g", nutrition.protein_g),
        ("fat_g", nutrition.fat_g),
        ("carbs_g", nutrition.carbs_g),
        ("photo_url", photo),
    ):
        if value is None:
            missing.append(field)
    return ExternalProduct(
        barcode=barcode,
        found=True,
        name=name,
        brand=_clean_text(product.get("brands")),
        package_weight_g=package_weight,
        package_quantity=_clean_text(product.get("quantity"), 100),
        package_quantity_unit=package_unit,
        serving_size=_clean_text(product.get("serving_size"), 100),
        nutrition_per_100g=nutrition,
        photo_url=photo,
        missing_fields=tuple(missing),
        derived_fields=tuple(derived),
    )


def last_modified_at(payload: dict[str, object]) -> datetime | None:
    product = payload.get("product")
    if not isinstance(product, dict):
        return None
    timestamp = decimal_value(product.get("last_modified_t"))
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), UTC)
    except (OverflowError, OSError, ValueError):
        return None


class OpenFoodFactsClient:
    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout_seconds: float,
        retries: int,
        concurrency: int,
        max_response_bytes: int,
        circuit_failures: int,
        circuit_cooldown_seconds: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            transport=transport,
        )
        self._retries = retries
        self._max_response_bytes = max_response_bytes
        self._circuit_failures = circuit_failures
        self._circuit_cooldown_seconds = circuit_cooldown_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._singleflight_lock = asyncio.Lock()
        self._inflight: dict[str, asyncio.Task[ExternalFetch]] = {}
        self._failure_count = 0
        self._circuit_until = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, barcode: str) -> ExternalFetch:
        async with self._singleflight_lock:
            task = self._inflight.get(barcode)
            owner = task is None
            if task is None:
                task = asyncio.create_task(self._fetch_with_retries(barcode))
                self._inflight[barcode] = task
        try:
            return await asyncio.shield(task)
        finally:
            if owner:
                async with self._singleflight_lock:
                    self._inflight.pop(barcode, None)

    async def _fetch_with_retries(self, barcode: str) -> ExternalFetch:
        if monotonic() < self._circuit_until:
            raise ExternalProductUnavailable("Open Food Facts временно недоступен.")
        started = monotonic()
        status: int | str = "error"
        try:
            for attempt in range(self._retries + 1):
                try:
                    result = await self._request(barcode)
                    status = result.http_status
                    self._failure_count = 0
                    return result
                except ExternalProductRateLimited:
                    status = 429
                    raise
                except (
                    httpx.TimeoutException,
                    ExternalProductUnavailable,
                ) as error:
                    status = (
                        "timeout"
                        if isinstance(error, httpx.TimeoutException)
                        else "5xx"
                    )
                    if attempt >= self._retries:
                        raise ExternalProductUnavailable(
                            "Open Food Facts временно недоступен. Попробуйте позже."
                        ) from error
                    await asyncio.sleep(0.1 * (attempt + 1))
        except (ExternalProductUnavailable, ExternalProductInvalidResponse):
            self._failure_count += 1
            if self._failure_count >= self._circuit_failures:
                self._circuit_until = monotonic() + self._circuit_cooldown_seconds
            raise
        finally:
            suffix = barcode[-4:]
            barcode_hash = hashlib.sha256(barcode.encode()).hexdigest()[:12]
            logger.info(
                "External product lookup provider=%s barcode_hash=%s "
                "suffix=%s status=%s duration_ms=%d",
                PROVIDER,
                barcode_hash,
                suffix,
                status,
                int((monotonic() - started) * 1000),
                extra={"operation": "external_product.lookup"},
            )
        raise RuntimeError("Unreachable lookup state")

    async def _request(self, barcode: str) -> ExternalFetch:
        async with self._semaphore:
            async with self._client.stream(
                "GET",
                f"/api/v2/product/{barcode}.json",
                params={"fields": REQUEST_FIELDS},
            ) as response:
                if response.status_code == 429:
                    raise ExternalProductRateLimited(
                        "Open Food Facts ограничил частоту запросов."
                    )
                if response.status_code >= 500:
                    raise ExternalProductUnavailable(
                        "Open Food Facts временно недоступен."
                    )
                if response.status_code == 404:
                    return ExternalFetch(404, {"status": 0})
                if response.status_code != 200:
                    raise ExternalProductInvalidResponse(
                        "Некорректный ответ Open Food Facts."
                    )
                content_type = response.headers.get("content-type", "").lower()
                if "application/json" not in content_type:
                    raise ExternalProductInvalidResponse(
                        "Open Food Facts вернул не JSON."
                    )
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = 0
                    if declared_size > self._max_response_bytes:
                        raise ExternalProductInvalidResponse(
                            "Ответ Open Food Facts слишком большой."
                        )
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise ExternalProductInvalidResponse(
                            "Ответ Open Food Facts слишком большой."
                        )
        try:
            payload: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ExternalProductInvalidResponse(
                "Open Food Facts вернул поврежденный JSON."
            ) from error
        if not isinstance(payload, dict):
            raise ExternalProductInvalidResponse("Некорректный ответ Open Food Facts.")
        return ExternalFetch(200, payload)
