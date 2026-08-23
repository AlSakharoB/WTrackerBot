from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import sharing_dish as dish_handlers
from app.bot.handlers import sharing_dish_batch as batch_handlers
from app.bot.keyboards.sharing_dish_batch import (
    DishSelectionItemCallback,
    build_dish_batch_preview_keyboard,
    build_dish_selection_search_keyboard,
)
from app.db.models import SharePackage, User
from app.search import SearchResult
from app.services.sharing import (
    BatchDishImportPlan,
    BatchDishPlanItem,
    BatchDishPreflight,
    BatchIngredientPreflight,
    DishConflictType,
    DishImportAction,
    DishNamePreflight,
    DishPackageAccess,
)
from app.sharing.payloads import (
    DishSharePayload,
    SharedDish,
    SharedDishComponent,
    SharedIngredient,
    SharePayloadLimits,
)


def batch_payload() -> DishSharePayload:
    ingredient = SharedIngredient(
        key="i1",
        name="Яйцо",
        kcal_per_100g=Decimal("150"),
        protein_per_100g=Decimal("12"),
        fat_per_100g=Decimal("10"),
        carbs_per_100g=Decimal("1"),
    )
    return DishSharePayload(
        ingredients=[ingredient],
        dishes=[
            SharedDish(
                key="d1",
                name="Омлет",
                components=[
                    SharedDishComponent(ingredient_key="i1", grams=Decimal("100"))
                ],
            ),
            SharedDish(
                key="d2",
                name="Яичный салат",
                components=[
                    SharedDishComponent(ingredient_key="i1", grams=Decimal("80"))
                ],
            ),
        ],
    )


def batch_context_values():
    payload = batch_payload()
    dishes = tuple(
        DishNamePreflight(dish, DishConflictType.NEW, None) for dish in payload.dishes
    )
    preflight = BatchDishPreflight(dishes, BatchIngredientPreflight(()))
    plan = BatchDishImportPlan(
        ingredients=(),
        dishes=tuple(
            BatchDishPlanItem(item, DishImportAction.CREATE) for item in dishes
        ),
    )
    return payload, preflight, plan


async def test_multi_dish_start_delegates_before_single_preflight(monkeypatch) -> None:
    payload = batch_payload()
    package = SharePackage(
        id=101,
        owner_user_id=1,
        payload=payload.model_dump(mode="json"),
        item_count=2,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = DishPackageAccess(package, payload, None, False)
    delegate = AsyncMock()
    monkeypatch.setattr(batch_handlers, "handle_dish_batch_share_start", delegate)
    message = AsyncMock(spec=Message)
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    user = User(id=2, telegram_id=200, timezone="Europe/Moscow")

    await dish_handlers.handle_dish_share_start(
        message,
        state,
        user,
        access,
        service,
    )

    delegate.assert_awaited_once_with(message, state, user, access, service)


async def test_batch_preview_fsm_stores_only_ids_and_decisions(monkeypatch) -> None:
    payload, preflight, plan = batch_context_values()
    package = SharePackage(
        id=102,
        owner_user_id=1,
        payload=payload.model_dump(mode="json"),
        item_count=2,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = DishPackageAccess(package, payload, None, False)
    service = Mock(
        preflight_dish_batch=AsyncMock(return_value=preflight),
        build_dish_batch_import_plan=AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(batch_handlers, "generate_action_token", lambda: "action123")
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await batch_handlers.handle_dish_batch_share_start(
        message,
        state,
        User(id=2, telegram_id=200, timezone="Europe/Moscow"),
        access,
        service,
    )

    state.update_data.assert_awaited_once_with(
        package_id=102,
        action_token="action123",
        ingredient_decisions={},
        dish_decisions={},
    )
    stored = state.update_data.await_args.kwargs
    assert "payload" not in stored
    assert "token" not in stored


def test_dish_selection_search_preserves_markers_and_callback_limits() -> None:
    results = [
        SearchResult(entity_id=1, name="Омлет", score=Decimal("10")),
        SearchResult(entity_id=2, name="Салат", score=Decimal("9")),
    ]

    keyboard = build_dish_selection_search_keyboard(results, {2})

    assert keyboard.inline_keyboard[0][0].text.startswith("⬜")
    assert keyboard.inline_keyboard[1][0].text.startswith("☑️")
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data is not None:
                assert len(button.callback_data.encode()) <= 64


async def test_dish_selection_toggle_removes_duplicate_and_keeps_other_ids(
    monkeypatch,
) -> None:
    service = Mock(get=AsyncMock(return_value=Mock()))
    render = AsyncMock()
    monkeypatch.setattr(batch_handlers, "DishService", lambda _: service)
    monkeypatch.setattr(batch_handlers, "_render_selection", render)
    state = Mock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"selected_ids": [1, 2]})
    state.update_data = AsyncMock()
    callback = Mock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback.message = Mock(spec=Message)

    await batch_handlers.dish_selection_toggle(
        callback,
        DishSelectionItemCallback(dish_id=2, page=3),
        state,
        User(id=10, telegram_id=100, timezone="Europe/Moscow"),
        Mock(spec=AsyncSession),
        SharePayloadLimits(max_items=20),
    )

    state.update_data.assert_awaited_once_with(selected_ids=[1])
    render.assert_awaited_once()


def test_aggregate_preview_is_deterministic_and_bounded() -> None:
    payload, preflight, plan = batch_context_values()
    long_payload = payload.model_copy(
        update={
            "dishes": [
                dish.model_copy(update={"name": "A" + "<" * 254})
                for dish in payload.dishes
            ]
        }
    )

    text = batch_handlers.dish_batch_preview_card(long_payload, preflight, plan)
    keyboard = build_dish_batch_preview_keyboard(
        "action123",
        has_ingredient_conflicts=True,
        can_import=True,
    )

    assert "Блюд: 2" in text
    assert "Необходимых ингредиентов: 1" in text
    assert "A<" not in text
    assert "A&lt;" in text
    assert len(text) < 4096
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data is not None:
                assert len(button.callback_data.encode()) <= 64
