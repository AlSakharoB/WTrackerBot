from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import monotonic

from app.barcodes import normalize_gtin
from app.exceptions import ValidationError
from app.integrations.open_food_facts import (
    PROVIDER,
    ExternalProduct,
    OpenFoodFactsClient,
    last_modified_at,
    parse_open_food_facts,
)
from app.repositories.external_products import ExternalProductRepository


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int


class BarcodeRateLimiter:
    def __init__(self, count: int, window_seconds: int) -> None:
        self._count = count
        self._window = window_seconds
        self._buckets: dict[int, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, user_id: int) -> RateLimitResult:
        async with self._lock:
            now = monotonic()
            bucket = self._buckets[user_id]
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._count:
                return RateLimitResult(
                    False, max(1, int(bucket[0] + self._window - now) + 1)
                )
            bucket.append(now)
            return RateLimitResult(True, 0)


class BarcodeConfirmationSigner:
    def __init__(self, secret: str, ttl_seconds: int) -> None:
        self._secret = secret.encode()
        self._ttl = ttl_seconds

    def issue(self, user_id: int, barcode: str, *, now: datetime | None = None) -> str:
        issued_at = int((now or datetime.now(UTC)).timestamp())
        payload = json.dumps(
            {"v": 1, "user_id": user_id, "barcode": barcode, "iat": issued_at},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
        return f"{encoded}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"

    def verify(
        self,
        token: str,
        user_id: int,
        barcode: str,
        *,
        now: datetime | None = None,
    ) -> None:
        try:
            encoded, signature_text = token.split(".", 1)
            expected = hmac.new(self._secret, encoded.encode(), hashlib.sha256).digest()
            signature = base64.urlsafe_b64decode(
                signature_text + "=" * (-len(signature_text) % 4)
            )
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(
                base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
            )
            issued_at = datetime.fromtimestamp(int(payload["iat"]), UTC)
        except (
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
            binascii.Error,
            UnicodeDecodeError,
            OverflowError,
            OSError,
        ) as error:
            raise ValidationError(
                "Подтверждение сканирования недействительно."
            ) from error
        current = now or datetime.now(UTC)
        if (
            payload.get("v") != 1
            or payload.get("user_id") != user_id
            or payload.get("barcode") != barcode
            or issued_at > current + timedelta(seconds=30)
            or current - issued_at > timedelta(seconds=self._ttl)
        ):
            raise ValidationError(
                "Подтверждение сканирования устарело или недействительно."
            )


class BarcodeLookupService:
    def __init__(
        self,
        repository: ExternalProductRepository,
        client: OpenFoodFactsClient,
        *,
        positive_cache_seconds: int,
        negative_cache_seconds: int,
    ) -> None:
        self._repository = repository
        self._client = client
        self._positive_ttl = positive_cache_seconds
        self._negative_ttl = negative_cache_seconds

    async def lookup(
        self, raw_barcode: str, *, now: datetime | None = None
    ) -> ExternalProduct:
        barcode = normalize_gtin(raw_barcode)
        current = now or datetime.now(UTC)
        cached = await self._repository.get_cached(PROVIDER, barcode, current)
        if cached is not None:
            return parse_open_food_facts(cached.response_json, barcode)

        fetched = await self._client.fetch(barcode)
        product = parse_open_food_facts(fetched.response_json, barcode)
        ttl = self._positive_ttl if product.found else self._negative_ttl
        await self._repository.cache(
            provider=PROVIDER,
            barcode=barcode,
            response_json=fetched.response_json,
            http_status=fetched.http_status,
            fetched_at=current,
            expires_at=current + timedelta(seconds=ttl),
            last_modified_at=last_modified_at(fetched.response_json),
        )
        return product
