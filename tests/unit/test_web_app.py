from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models.user import User
from app.services.users import UserSyncResult
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.unit.test_web_auth import BOT_TOKEN, sign_init_data


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "bot_token": BOT_TOKEN,
        "database_url": "postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
        "app_version": "0.2.0",
        "miniapp_enabled": True,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def make_client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    )


async def test_healthcheck_is_public() -> None:
    app = create_web_app(make_settings())
    async with make_client(app) as client:
        response = await client.get("/internal/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.2.0"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-correlation-id"]


async def test_disabled_miniapp_keeps_health_public_and_blocks_api() -> None:
    app = create_web_app(make_settings(miniapp_enabled=False))
    async with make_client(app) as client:
        health_response = await client.get("/internal/healthz")
        api_response = await client.get("/api/v1/me")

    assert health_response.status_code == 200
    assert api_response.status_code == 503
    assert api_response.headers["retry-after"] == "60"
    assert api_response.json()["error"]["code"] == "miniapp_disabled"


async def test_miniapp_allowlist_uses_only_signed_telegram_id() -> None:
    app = create_web_app(
        make_settings(miniapp_allowed_telegram_ids={987654321}),
    )
    async with make_client(app) as client:
        response = await client.get(
            "/api/v1/me?telegram_id=987654321",
            headers={
                "Authorization": (f"tma {sign_init_data(auth_date=datetime.now(UTC))}")
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "miniapp_not_available"


async def test_me_requires_telegram_authorization() -> None:
    app = create_web_app(make_settings())
    async with make_client(app) as client:
        response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "tma"
    assert response.json()["error"]["code"] == "authentication_failed"
    assert response.json()["error"]["correlation_id"]


@pytest.mark.parametrize(
    "init_data",
    [
        sign_init_data(auth_date=datetime(2020, 1, 1, tzinfo=UTC)),
        sign_init_data(auth_date=datetime.now(UTC)).replace("279058397", "999999999"),
    ],
)
async def test_me_rejects_expired_or_tampered_init_data(init_data: str) -> None:
    app = create_web_app(make_settings())
    async with make_client(app) as client:
        response = await client.get(
            "/api/v1/me",
            headers={"Authorization": f"tma {init_data}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_me_rejects_oversized_authorization_header() -> None:
    app = create_web_app(make_settings(miniapp_max_auth_header_bytes=512))
    async with make_client(app) as client:
        response = await client.get(
            "/api/v1/me",
            headers={"Authorization": "tma " + "x" * 600},
        )

    assert response.status_code == 401


async def test_me_syncs_only_signed_telegram_user(monkeypatch) -> None:
    settings = make_settings()
    app = create_web_app(settings)
    fake_session = Mock(spec=AsyncSession)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield fake_session

    app.dependency_overrides[get_database_session] = override_session
    user = User(
        id=7,
        telegram_id=279058397,
        username="example_user",
        first_name="Vladislav",
        last_name="Sakharov",
        language_code="ru",
        timezone="Europe/Moscow",
    )
    sync = AsyncMock(return_value=UserSyncResult(user=user, created=False))
    monkeypatch.setattr("app.web.dependencies.UserService.sync_telegram_user", sync)

    async with make_client(app) as client:
        response = await client.get(
            "/api/v1/me",
            headers={
                "Authorization": (f"tma {sign_init_data(auth_date=datetime.now(UTC))}")
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": "7",
        "telegram_id": "279058397",
        "username": "example_user",
        "first_name": "Vladislav",
        "last_name": "Sakharov",
        "language_code": "ru",
        "timezone": "Europe/Moscow",
        "app_version": "0.2.0",
    }
    synced_data = sync.await_args.args[0]
    assert synced_data.telegram_id == 279058397


async def test_request_body_limit_returns_structured_error() -> None:
    app = create_web_app(make_settings(miniapp_max_request_body_bytes=1024))
    async with make_client(app) as client:
        response = await client.post(
            "/missing",
            headers={"Content-Length": "1025"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


async def test_streamed_request_body_cannot_bypass_limit() -> None:
    async def body() -> AsyncIterator[bytes]:
        yield b"x" * 700
        yield b"y" * 700

    app = create_web_app(make_settings(miniapp_max_request_body_bytes=1024))
    async with make_client(app) as client:
        response = await client.post("/missing", content=body())

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


async def test_not_found_uses_error_envelope() -> None:
    app = create_web_app(make_settings())
    async with make_client(app) as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("correlation_id", ["request-123", "bad id value"])
async def test_correlation_id_is_sanitized(correlation_id: str) -> None:
    app = create_web_app(make_settings())
    async with make_client(app) as client:
        response = await client.get(
            "/internal/healthz",
            headers={"X-Correlation-ID": correlation_id},
        )

    if correlation_id == "request-123":
        assert response.headers["x-correlation-id"] == correlation_id
    else:
        assert response.headers["x-correlation-id"] != correlation_id
