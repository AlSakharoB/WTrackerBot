from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.repositories.users import UserRepository
from app.repositories.web_mutations import WebMutationReceiptRepository
from app.services.web_mutations import WebMutationService
from app.web.app import create_web_app
from app.web.dependencies import get_database_session
from tests.unit.test_web_auth import BOT_TOKEN, sign_init_data


async def test_signed_user_and_idempotent_mutation_share_database(
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
    auth_date = datetime.now(UTC)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/me",
            headers={"Authorization": f"tma {sign_init_data(auth_date=auth_date)}"},
        )

    assert response.status_code == 200
    user = await UserRepository(session).get_by_telegram_id(279058397)
    assert user is not None
    assert response.json()["id"] == str(user.id)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as preferences_client:
        auth_header = {"Authorization": f"tma {sign_init_data(auth_date=auth_date)}"}
        preferences_response = await preferences_client.get(
            "/api/v1/ui-preferences",
            headers=auth_header,
        )
        assert preferences_response.status_code == 200
        assert preferences_response.json()["theme_mode"] == "system"
        assert preferences_response.json()["default_section"] == "ration"
        assert preferences_response.json()["default_weight_unit"] == "kg"
        assert preferences_response.json()["compact_lists"] is False

        update_response = await preferences_client.patch(
            "/api/v1/ui-preferences",
            headers=auth_header,
            json={"theme_mode": "dark", "compact_lists": True},
        )
        assert update_response.status_code == 200
        assert update_response.json()["theme_mode"] == "dark"
        assert update_response.json()["compact_lists"] is True

        persisted_response = await preferences_client.get(
            "/api/v1/ui-preferences",
            headers=auth_header,
        )
        assert persisted_response.json()["theme_mode"] == "dark"
        assert persisted_response.json()["compact_lists"] is True

        second_user_auth = sign_init_data(
            auth_date=auth_date,
            user={"id": 987654321, "first_name": "Second"},
        )
        second_user_response = await preferences_client.get(
            "/api/v1/ui-preferences",
            headers={"Authorization": f"tma {second_user_auth}"},
        )
        assert second_user_response.status_code == 200
        assert second_user_response.json()["theme_mode"] == "system"
        assert second_user_response.json()["compact_lists"] is False

        empty_update_response = await preferences_client.patch(
            "/api/v1/ui-preferences",
            headers=auth_header,
            json={},
        )
        assert empty_update_response.status_code == 422

    service = WebMutationService(
        WebMutationReceiptRepository(session),
        receipt_ttl_hours=24,
    )
    command = AsyncMock(return_value=(201, {"id": "created"}))
    first = await service.execute(
        user_id=user.id,
        operation="test.create",
        idempotency_key="integration-request",
        payload={"value": "same"},
        command=command,
        now=auth_date,
    )
    replay = await service.execute(
        user_id=user.id,
        operation="test.create",
        idempotency_key="integration-request",
        payload={"value": "same"},
        command=command,
        now=auth_date,
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.body == {"id": "created"}
    command.assert_awaited_once()
