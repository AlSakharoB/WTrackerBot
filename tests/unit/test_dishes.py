from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers import dishes as dish_handlers
from app.bot.handlers.dishes import dish_editor_save, dish_name_message
from app.bot.keyboards.actions import DISH_SAVE_ACTION, ConfirmActionCallback
from app.bot.keyboards.dishes import (
    DishCallback,
    DishIngredientCallback,
    DishIngredientPageCallback,
)
from app.db.models.dish import Dish
from app.db.models.ingredient import Ingredient
from app.db.models.user import User
from app.exceptions import DuplicateError, NotFoundError, ValidationError
from app.services.dishes import (
    DishComponentData,
    DishService,
    normalize_dish_name,
    parse_component_grams,
)


def make_ingredient(ingredient_id: int, name: str) -> Ingredient:
    return Ingredient(
        id=ingredient_id,
        user_id=10,
        name=name,
        name_normalized=name.lower(),
        kcal_per_100g=Decimal("100"),
        protein_per_100g=Decimal("10"),
        fat_per_100g=Decimal("5"),
        carbs_per_100g=Decimal("20"),
    )


def test_normalize_dish_name() -> None:
    assert normalize_dish_name("  Курица   с гречкой ") == (
        "Курица с гречкой",
        "курица с гречкой",
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("1", Decimal("1")),
        ("150.5", Decimal("150.5")),
        ("150,5", Decimal("150.5")),
    ],
)
def test_parse_component_grams(raw_value: str, expected: Decimal) -> None:
    assert parse_component_grams(raw_value) == expected


@pytest.mark.parametrize("raw_value", ["0", "-1", "abc", "NaN", "1000000.01"])
def test_parse_component_grams_rejects_invalid_value(raw_value: str) -> None:
    with pytest.raises(ValidationError):
        parse_component_grams(raw_value)


async def test_create_validates_ingredients_and_returns_dynamic_nutrition() -> None:
    ingredient = make_ingredient(1, "Гречка")
    dish = Dish(id=5, user_id=10, name="Гречка", name_normalized="гречка")
    repository = Mock()
    repository.get_ingredients = AsyncMock(return_value=[ingredient])
    repository.find_similar_names = AsyncMock(return_value=[])
    repository.create = AsyncMock(return_value=dish)
    service = DishService(repository)

    details = await service.create(
        10,
        " Гречка ",
        [DishComponentData(ingredient_id=1, grams=Decimal("250"))],
    )

    assert details.nutrition.total_weight == Decimal("250")
    assert details.nutrition.total.kcal == Decimal("250.0")
    repository.create.assert_awaited_once_with(
        user_id=10,
        name="Гречка",
        name_normalized="гречка",
        components=[(1, Decimal("250"))],
    )


async def test_create_rejects_similar_existing_dish_name() -> None:
    ingredient = make_ingredient(1, "Яйцо")
    existing = Dish(
        id=5,
        user_id=10,
        name="Омлет с грибами и сыром",
        name_normalized="омлет с грибами и сыром",
    )
    repository = Mock()
    repository.get_ingredients = AsyncMock(return_value=[ingredient])
    repository.find_similar_names = AsyncMock(return_value=[existing])
    repository.create = AsyncMock()
    service = DishService(repository)

    with pytest.raises(DuplicateError, match="Омлет с грибами и сыром"):
        await service.create(
            10,
            "Омлет с грибами и сырома",
            [DishComponentData(ingredient_id=1, grams=Decimal("100"))],
        )

    repository.create.assert_not_awaited()


async def test_name_step_cancels_creation_for_similar_dish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = AsyncMock(spec=Message)
    message.text = "Омлет с сырома"
    message.answer = AsyncMock()
    state = AsyncMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value={"mode": "create"})
    service = Mock()
    service.check_name_available = AsyncMock(
        side_effect=DuplicateError("Похожее блюдо «Омлет с сыром» уже существует.")
    )
    monkeypatch.setattr(dish_handlers, "dish_service", lambda session: service)

    await dish_name_message(
        message,
        state,
        current_user=User(id=10, telegram_id=100, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    state.clear.assert_awaited_once()
    state.update_data.assert_not_awaited()
    assert "Омлет с сыром" in message.answer.await_args.args[0]
    assert "Добавление отменено" in message.answer.await_args.args[0]


async def test_duplicate_rename_keeps_dish_editor_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callback = AsyncMock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    callback_message = AsyncMock(spec=Message)
    callback_message.edit_text = AsyncMock()
    callback.message = callback_message
    state = AsyncMock(spec=FSMContext)
    service = Mock()
    service.replace = AsyncMock(
        side_effect=DuplicateError("Блюдо с таким названием уже существует.")
    )
    monkeypatch.setattr(dish_handlers, "dish_service", lambda session: service)
    monkeypatch.setattr(
        dish_handlers,
        "confirmation_data",
        AsyncMock(
            return_value={
                "mode": "edit",
                "dish_id": 5,
                "name": "Омлет",
                "components": [],
                "page": 1,
            }
        ),
    )

    await dish_editor_save(
        callback,
        ConfirmActionCallback(action=DISH_SAVE_ACTION, token="token"),
        state,
        current_user=User(id=10, telegram_id=100, timezone="Europe/Moscow"),
        db_session=Mock(spec=AsyncSession),
    )

    callback.answer.assert_awaited_once_with(
        "Блюдо с таким названием уже существует.",
        show_alert=True,
    )
    state.clear.assert_not_awaited()
    callback_message.edit_text.assert_not_awaited()


async def test_create_rejects_empty_and_duplicate_components() -> None:
    repository = Mock()
    service = DishService(repository)

    with pytest.raises(ValidationError):
        await service.create(10, "Пустое", [])
    with pytest.raises(DuplicateError):
        await service.create(
            10,
            "Дубли",
            [
                DishComponentData(1, Decimal("100")),
                DishComponentData(1, Decimal("200")),
            ],
        )


async def test_create_rejects_foreign_ingredient() -> None:
    repository = Mock()
    repository.get_ingredients = AsyncMock(return_value=[])
    service = DishService(repository)

    with pytest.raises(NotFoundError):
        await service.create(
            10,
            "Чужой продукт",
            [DishComponentData(999, Decimal("100"))],
        )


def test_dish_callbacks_fit_telegram_limit() -> None:
    callbacks = [
        DishCallback(
            action="delete_confirm",
            dish_id=9_223_372_036_854_775_807,
            page=999_999,
        ).pack(),
        DishIngredientCallback(
            action="select",
            ingredient_id=9_223_372_036_854_775_807,
        ).pack(),
        DishIngredientPageCallback(page=999_999).pack(),
    ]

    assert all(len(callback.encode()) <= 64 for callback in callbacks)
