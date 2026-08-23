from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import sharing as sharing_handlers
from app.bot.handlers import start as start_handlers
from app.bot.handlers.sharing import (
    conflict_card,
    handle_ingredient_share_start,
    import_preview_card,
    share_import_confirm_callback,
)
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.sharing import (
    SHARE_IMPORT_ACTION,
    SharePackageCallback,
    build_import_preview_keyboard,
)
from app.db.models import Ingredient, SharePackage, User
from app.services.sharing import (
    IngredientConflictType,
    IngredientPackageAccess,
    IngredientPreflight,
)
from app.sharing.payloads import (
    IngredientSharePayload,
    SharedIngredient,
    SharePayloadLimits,
)


def shared_ingredient(name: str = "Куриная грудка") -> SharedIngredient:
    return SharedIngredient(
        key="i1",
        name=name,
        kcal_per_100g=Decimal("165.00"),
        protein_per_100g=Decimal("31.00"),
        fat_per_100g=Decimal("3.60"),
        carbs_per_100g=Decimal("0.00"),
    )


def test_start_payload_parser_supports_bot_suffix() -> None:
    assert start_handlers.extract_start_payload("/start sh_token") == "sh_token"
    assert (
        start_handlers.extract_start_payload("/start@nutrition_test_bot sh_token")
        == "sh_token"
    )
    assert start_handlers.extract_start_payload("/start") is None
    assert start_handlers.extract_start_payload("hello") is None


async def test_share_start_is_handled_before_welcome(monkeypatch) -> None:
    message = AsyncMock(spec=Message)
    message.text = "startup text"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    handler = AsyncMock()
    monkeypatch.setattr(start_handlers, "extract_start_payload", lambda _: "sh_token")
    monkeypatch.setattr(start_handlers, "handle_ingredient_share_start", handler)
    user = User(id=10, telegram_id=100, timezone="Europe/Moscow")
    session = Mock(spec=AsyncSession)
    limits = SharePayloadLimits()

    await start_handlers.start_handler(
        message,
        current_user=user,
        is_new_user=True,
        state=state,
        db_session=session,
        bot_username="nutrition_test_bot",
        share_link_ttl_days=30,
        share_payload_limits=limits,
    )

    state.clear.assert_awaited_once()
    handler.assert_awaited_once_with(
        message,
        state,
        user,
        session,
        "sh_token",
        bot_username="nutrition_test_bot",
        share_link_ttl_days=30,
        share_payload_limits=limits,
    )
    message.answer.assert_not_awaited()


async def test_recipient_preview_only_stores_package_and_action_token(
    monkeypatch,
) -> None:
    incoming = shared_ingredient()
    package = SharePackage(
        id=55,
        owner_user_id=1,
        package_type="ingredients",
        payload_version=1,
        payload=IngredientSharePayload(ingredients=[incoming]).model_dump(mode="json"),
        item_count=1,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = IngredientPackageAccess(
        package=package,
        payload=IngredientSharePayload(ingredients=[incoming]),
        previous_import=None,
        is_owner=False,
    )
    service = Mock(resolve_ingredient_token=AsyncMock(return_value=access))
    monkeypatch.setattr(sharing_handlers, "sharing_service", lambda *_, **__: service)
    monkeypatch.setattr(sharing_handlers, "generate_action_token", lambda: "action123")
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await handle_ingredient_share_start(
        message,
        state,
        User(id=2, telegram_id=200, timezone="Europe/Moscow"),
        Mock(spec=AsyncSession),
        "sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        bot_username="nutrition_test_bot",
        share_link_ttl_days=30,
        share_payload_limits=SharePayloadLimits(),
    )

    state.update_data.assert_awaited_once_with(
        package_id=55,
        action_token="action123",
    )
    stored = state.update_data.await_args.kwargs
    assert "token" not in stored
    assert "payload" not in stored
    message.answer.assert_awaited_once()
    assert "Вам отправили ингредиент" in message.answer.await_args.args[0]


def test_import_callbacks_contain_no_package_or_source_ids() -> None:
    keyboard = build_import_preview_keyboard("action123")
    callback_data = keyboard.inline_keyboard[0][0].callback_data

    assert callback_data is not None
    parsed = ConfirmActionCallback.unpack(callback_data)
    assert parsed.action == SHARE_IMPORT_ACTION
    assert parsed.token == "action123"
    assert "55" not in callback_data


def test_sender_share_callback_fits_telegram_limit() -> None:
    callback_data = SharePackageCallback(
        action="revoke",
        package_id=9_223_372_036_854_775_807,
        ingredient_id=9_223_372_036_854_775_807,
        page=999_999,
    ).pack()

    assert len(callback_data.encode()) <= 64


async def test_foreign_or_stale_import_callback_stops_before_service(
    monkeypatch,
) -> None:
    callback = Mock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    state = Mock(spec=FSMContext)
    state.get_data = AsyncMock(
        return_value={"package_id": 55, "action_token": "current-token"}
    )
    factory = Mock()
    monkeypatch.setattr(sharing_handlers, "sharing_service", factory)

    await share_import_confirm_callback(
        callback,
        ConfirmActionCallback(action=SHARE_IMPORT_ACTION, token="foreign-token"),
        state,
        User(id=2, telegram_id=200, timezone="Europe/Moscow"),
        Mock(spec=AsyncSession),
        bot_username="nutrition_test_bot",
        share_link_ttl_days=30,
        share_payload_limits=SharePayloadLimits(),
    )

    callback.answer.assert_awaited_once()
    factory.assert_not_called()


def test_recipient_and_conflict_cards_escape_html_names() -> None:
    incoming = shared_ingredient("<script>Курица</script>")
    existing = Ingredient(
        id=1,
        user_id=2,
        name="<b>Моя курица</b>",
        name_normalized="моя курица",
        kcal_per_100g=Decimal("170"),
        protein_per_100g=Decimal("30"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("0"),
    )

    preview = import_preview_card(incoming)
    conflict = conflict_card(
        IngredientPreflight(
            IngredientConflictType.NAME_CONFLICT,
            incoming,
            existing,
        )
    )

    assert "<script>" not in preview
    assert "&lt;script&gt;" in preview
    assert "<b>Моя курица</b>" not in conflict
    assert "&lt;b&gt;Моя курица&lt;/b&gt;" in conflict
