from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import sharing as sharing_handlers
from app.bot.handlers import sharing_dish as dish_handlers
from app.bot.handlers.sharing import handle_ingredient_share_start
from app.bot.keyboards.actions import ConfirmActionCallback
from app.bot.keyboards.sharing_dish import (
    DISH_IMPORT_ACTION,
    DishImportCallback,
    build_dish_import_preview_keyboard,
)
from app.db.models import SharePackage, User
from app.services.sharing import (
    BatchIngredientPreflight,
    CreatedSharePackage,
    DishConflictType,
    DishImportAction,
    DishImportPlan,
    DishPackageAccess,
    DishPreflight,
    InvalidShareLinkError,
)
from app.sharing.payloads import (
    DishSharePayload,
    SharedDish,
    SharedDishComponent,
    SharedIngredient,
    SharePayloadLimits,
)


def dish_payload(component_count: int = 1) -> DishSharePayload:
    ingredients = [
        SharedIngredient(
            key=f"i{index}",
            name=f"Ингредиент {index}",
            kcal_per_100g=Decimal("100"),
            protein_per_100g=Decimal("10"),
            fat_per_100g=Decimal("5"),
            carbs_per_100g=Decimal("12"),
        )
        for index in range(1, component_count + 1)
    ]
    return DishSharePayload(
        ingredients=ingredients,
        dishes=[
            SharedDish(
                key="d1",
                name="Тестовое блюдо",
                components=[
                    SharedDishComponent(
                        ingredient_key=item.key,
                        grams=Decimal("100"),
                    )
                    for item in ingredients
                ],
            )
        ],
    )


async def test_start_falls_back_from_ingredient_to_dish_package(monkeypatch) -> None:
    payload = dish_payload()
    package = SharePackage(
        id=90,
        owner_user_id=1,
        payload=payload.model_dump(mode="json"),
        item_count=1,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = DishPackageAccess(package, payload, None, False)
    service = Mock(
        resolve_ingredient_token=AsyncMock(side_effect=InvalidShareLinkError("bad")),
        resolve_dish_token=AsyncMock(return_value=access),
    )
    delegate = AsyncMock()
    monkeypatch.setattr(sharing_handlers, "sharing_service", lambda *_, **__: service)
    monkeypatch.setattr(dish_handlers, "handle_dish_share_start", delegate)
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    user = User(id=2, telegram_id=200, timezone="Europe/Moscow")

    await handle_ingredient_share_start(
        message,
        state,
        user,
        Mock(spec=AsyncSession),
        "sh_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        bot_username="nutrition_test_bot",
        share_link_ttl_days=30,
        share_payload_limits=SharePayloadLimits(),
    )

    delegate.assert_awaited_once_with(message, state, user, access, service)
    message.answer.assert_not_awaited()


async def test_dish_preview_fsm_stores_only_identifiers_and_decisions(
    monkeypatch,
) -> None:
    payload = dish_payload()
    package = SharePackage(
        id=91,
        owner_user_id=1,
        payload=payload.model_dump(mode="json"),
        item_count=1,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    access = DishPackageAccess(package, payload, None, False)
    preflight = DishPreflight(
        dish=payload.dishes[0],
        conflict_type=DishConflictType.NEW,
        existing=None,
        ingredients=BatchIngredientPreflight(()),
    )
    plan = DishImportPlan(
        dish=payload.dishes[0],
        dish_conflict_type=DishConflictType.NEW,
        dish_action=DishImportAction.CREATE,
        existing_dish=None,
        ingredients=(),
    )
    service = Mock(
        preflight_dish=AsyncMock(return_value=preflight),
        build_dish_import_plan=AsyncMock(return_value=plan),
    )
    monkeypatch.setattr(dish_handlers, "generate_action_token", lambda: "action123")
    message = AsyncMock(spec=Message)
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)

    await dish_handlers.handle_dish_share_start(
        message,
        state,
        User(id=2, telegram_id=200, timezone="Europe/Moscow"),
        access,
        service,
    )

    state.update_data.assert_awaited_once_with(
        package_id=91,
        action_token="action123",
        ingredient_decisions={},
        dish_decision=None,
    )
    stored = state.update_data.await_args.kwargs
    assert "payload" not in stored
    assert "token" not in stored


def test_dish_recipient_callbacks_contain_no_package_or_source_ids() -> None:
    keyboard = build_dish_import_preview_keyboard(
        "action123",
        ingredient_conflicts=True,
        dish_conflict=True,
        can_import=True,
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]

    confirm = next(item for item in callbacks if item.startswith("confirm:"))
    parsed = ConfirmActionCallback.unpack(confirm)
    assert parsed.action == DISH_IMPORT_ACTION
    assert parsed.token == "action123"
    for item in callbacks:
        assert len(item.encode()) <= 64
        assert "91" not in item
    conflict = next(item for item in callbacks if item.startswith("shdi:"))
    assert DishImportCallback.unpack(conflict).index == 0


def test_dish_sender_preview_is_bounded_and_uses_snapshot_nutrition() -> None:
    payload = dish_payload(100)
    malicious = payload.model_copy(
        update={
            "ingredients": [
                item.model_copy(update={"name": "A" + "<" * 254})
                for item in payload.ingredients
            ]
        }
    )
    package = SharePackage(
        id=92,
        owner_user_id=1,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    created = CreatedSharePackage(package, "token", "deep", "share")

    text = dish_handlers.created_dish_share_card(created, malicious)

    assert "И ещё: 92" in text
    assert "10000" in text
    assert "A<" not in text
    assert "A&lt;" in text
    assert len(text) < 4096
