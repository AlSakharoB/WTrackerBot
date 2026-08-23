from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import sharing_management as handlers
from app.bot.handlers.sharing_management import (
    management_detail_text,
    management_list_text,
    share_management_rotate_confirm_callback,
)
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.sharing_management import (
    SHARE_ROTATE_ACTION,
    ShareManagementCallback,
    build_share_management_keyboard,
)
from app.db.models import SharePackage, User
from app.db.models.share import SharePackageType
from app.services.sharing import (
    OwnedSharePackage,
    OwnedSharePackagePage,
    ShareRuntimeStatus,
)
from app.sharing.payloads import SharePayloadLimits


def managed_package(title: str = "Курица") -> OwnedSharePackage:
    now = datetime(2026, 8, 24, tzinfo=UTC)
    package = SharePackage(
        id=55,
        owner_user_id=7,
        package_type=SharePackageType.INGREDIENTS,
        payload_version=1,
        payload={},
        item_count=2,
        created_at=now,
        expires_at=now + timedelta(days=30),
    )
    return OwnedSharePackage(
        package=package,
        title=title,
        runtime_status=ShareRuntimeStatus.ACTIVE,
        completed_imports=3,
    )


def test_management_screen_has_required_data_without_recipient_identity() -> None:
    item = managed_package("<b>Курица</b>")
    page = OwnedSharePackagePage((item,), page=1, pages=1, total=1)

    list_text = management_list_text(
        page, SharePackageType.INGREDIENTS, "Europe/Moscow"
    )
    detail_text = management_detail_text(item, "Europe/Moscow")

    assert "&lt;b&gt;Курица&lt;/b&gt;" in list_text
    assert "Объектов: 2" in list_text
    assert "Завершённых импортов: 3" in detail_text
    assert "recipient" not in (list_text + detail_text).lower()
    assert "telegram" not in (list_text + detail_text).lower()


def test_management_callbacks_fit_telegram_limit() -> None:
    item = managed_package()
    page = OwnedSharePackagePage((item,), page=999_999, pages=999_999, total=1)
    keyboard = build_share_management_keyboard(page, SharePackageType.INGREDIENTS)

    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data is not None:
                assert len(button.callback_data.encode()) <= 64
    packed = ShareManagementCallback(
        action="rotate",
        package_type="ingredients",
        package_id=9_223_372_036_854_775_807,
        page=999_999,
    ).pack()
    assert len(packed.encode()) <= 64


async def test_stale_rotation_confirmation_stops_before_service(monkeypatch) -> None:
    callback = Mock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    state = Mock(spec=FSMContext)
    state.get_data = AsyncMock(
        return_value={
            "action_token": "current",
            "management_action": SHARE_ROTATE_ACTION,
            "package_id": 55,
            "page": 1,
        }
    )
    factory = Mock()
    monkeypatch.setattr(handlers, "sharing_service", factory)

    await share_management_rotate_confirm_callback(
        callback,
        ConfirmActionCallback(action=SHARE_ROTATE_ACTION, token="stale"),
        state,
        User(id=7, telegram_id=77, timezone="Europe/Moscow"),
        Mock(spec=AsyncSession),
        bot_username="test_bot",
        share_link_ttl_days=30,
        share_payload_limits=SharePayloadLimits(),
    )

    callback.answer.assert_awaited_once()
    factory.assert_not_called()
