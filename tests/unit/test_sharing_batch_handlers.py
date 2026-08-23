from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import sharing as sharing_handlers
from app.bot.handlers import sharing_batch as batch_handlers
from app.bot.handlers.sharing import handle_ingredient_share_start
from app.bot.keyboards.sharing_batch import (
    ShareSelectionItemCallback,
    build_selection_search_keyboard,
)
from app.db.models import Ingredient, SharePackage, User
from app.search import SearchResult
from app.services.sharing import IngredientPackageAccess
from app.sharing.payloads import (
    IngredientSharePayload,
    SharedIngredient,
    SharePayloadLimits,
)


def shared(key: str, name: str) -> SharedIngredient:
    return SharedIngredient(
        key=key,
        name=name,
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("12"),
    )


async def test_batch_start_delegates_without_storing_payload(monkeypatch) -> None:
    payload = IngredientSharePayload(
        ingredients=[shared("i1", "Первый"), shared("i2", "Второй")]
    )
    package = SharePackage(
        id=77,
        owner_user_id=1,
        payload=payload.model_dump(mode="json"),
        item_count=2,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = IngredientPackageAccess(package, payload, None, False)
    service = Mock(resolve_ingredient_token=AsyncMock(return_value=access))
    delegate = AsyncMock()
    monkeypatch.setattr(sharing_handlers, "sharing_service", lambda *_, **__: service)
    monkeypatch.setattr(batch_handlers, "handle_batch_ingredient_access", delegate)
    state = AsyncMock(spec=FSMContext)
    message = AsyncMock(spec=Message)

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

    delegate.assert_awaited_once()
    state.update_data.assert_not_awaited()


def test_search_keyboard_keeps_selected_markers_and_small_callbacks() -> None:
    results = [
        SearchResult(entity_id=1, name="Первый", score=Decimal("10")),
        SearchResult(entity_id=2, name="Второй", score=Decimal("9")),
    ]

    keyboard = build_selection_search_keyboard(results, {2})

    assert keyboard.inline_keyboard[0][0].text.startswith("⬜")
    assert keyboard.inline_keyboard[1][0].text.startswith("☑️")
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data is not None:
                assert len(button.callback_data.encode()) <= 64


async def test_selection_toggle_removes_duplicate_without_losing_other_ids(
    monkeypatch,
) -> None:
    ingredient = Ingredient(id=2, user_id=10, name="Второй")
    service = Mock(get=AsyncMock(return_value=ingredient))
    render = AsyncMock()
    monkeypatch.setattr(batch_handlers, "_ingredient_service", lambda _: service)
    monkeypatch.setattr(batch_handlers, "_render_selection_page", render)
    state = Mock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"selected_ids": [1, 2]})
    state.update_data = AsyncMock()
    callback = Mock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = Mock(spec=Message)

    await batch_handlers.share_selection_toggle(
        callback,
        ShareSelectionItemCallback(ingredient_id=2, page=3),
        state,
        User(id=10, telegram_id=100, timezone="Europe/Moscow"),
        Mock(spec=AsyncSession),
        SharePayloadLimits(max_items=20),
    )

    state.update_data.assert_awaited_once_with(selected_ids=[1])
    render.assert_awaited_once()


def test_batch_sender_preview_is_bounded_and_escapes_names() -> None:
    names = [f"<b>{index}</b>" + "я" * 255 for index in range(20)]

    text = batch_handlers.batch_created_card(names, "01.01.2027")

    assert "<b>0</b>" not in text
    assert "&lt;b&gt;0&lt;/b&gt;" in text
    assert "И ещё: 17" in text
    assert len(text) < 4096
