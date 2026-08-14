from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import DuplicateError, NotFoundError
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.repositories.users import UserRepository
from app.services.ingredients import (
    CreateIngredientData,
    IngredientField,
    IngredientService,
)
from app.services.search import SearchService
from app.services.users import TelegramUserData, UserService


async def create_user(session: AsyncSession, telegram_id: int) -> int:
    result = await UserService(
        UserRepository(session),
        default_timezone="Europe/Moscow",
    ).sync_telegram_user(
        TelegramUserData(
            telegram_id=telegram_id,
            username=None,
            first_name="Ingredient Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


def ingredient_data(name: str) -> CreateIngredientData:
    return CreateIngredientData(
        name=name,
        kcal_per_100g=Decimal("165"),
        protein_per_100g=Decimal("31"),
        fat_per_100g=Decimal("3.6"),
        carbs_per_100g=Decimal("0"),
    )


async def test_ingredient_crud_and_normalization(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9220000001)
    service = IngredientService(IngredientRepository(session))

    ingredient = await service.create(
        user_id,
        ingredient_data("  Куриная   грудка "),
    )
    found = await SearchService(SearchRepository(session)).search_ingredients(
        user_id,
        "груд",
    )
    updated = await service.update_field(
        user_id,
        ingredient.id,
        IngredientField.KCAL,
        "160,5",
    )

    assert ingredient.name == "Куриная грудка"
    assert ingredient.name_normalized == "куриная грудка"
    assert found[0].entity_id == ingredient.id
    assert updated.kcal_per_100g == Decimal("160.50")

    await service.delete(user_id, ingredient.id)
    with pytest.raises(NotFoundError):
        await service.get(user_id, ingredient.id)


async def test_ingredient_name_is_unique_only_within_user(
    session: AsyncSession,
) -> None:
    first_user_id = await create_user(session, 9220000002)
    second_user_id = await create_user(session, 9220000003)
    service = IngredientService(IngredientRepository(session))

    first = await service.create(first_user_id, ingredient_data("Авокадо"))
    banana = await service.create(first_user_id, ingredient_data("Банан"))
    second = await service.create(second_user_id, ingredient_data("  авокадо  "))

    assert first.id != second.id
    with pytest.raises(DuplicateError):
        await service.create(first_user_id, ingredient_data(" АВОКАДО "))
    with pytest.raises(DuplicateError):
        await service.update_field(
            first_user_id,
            banana.id,
            IngredientField.NAME,
            "авокадо",
        )

    assert (await service.get(first_user_id, banana.id)).name == "Банан"


async def test_user_cannot_read_update_or_delete_foreign_ingredient(
    session: AsyncSession,
) -> None:
    owner_id = await create_user(session, 9220000004)
    other_user_id = await create_user(session, 9220000005)
    service = IngredientService(IngredientRepository(session))
    ingredient = await service.create(owner_id, ingredient_data("Помидор"))

    with pytest.raises(NotFoundError):
        await service.get(other_user_id, ingredient.id)
    with pytest.raises(NotFoundError):
        await service.update_field(
            other_user_id,
            ingredient.id,
            IngredientField.NAME,
            "Чужой продукт",
        )
    with pytest.raises(NotFoundError):
        await service.delete(other_user_id, ingredient.id)

    assert (await service.get(owner_id, ingredient.id)).name == "Помидор"


async def test_ingredient_pagination_uses_eight_items(
    session: AsyncSession,
) -> None:
    user_id = await create_user(session, 9220000006)
    service = IngredientService(IngredientRepository(session))
    for index in range(9):
        await service.create(user_id, ingredient_data(f"Ингредиент {index}"))

    first_page = await service.list_page(user_id, 1)
    second_page = await service.list_page(user_id, 2)

    assert first_page.total == 9
    assert first_page.pages == 2
    assert len(first_page.items) == 8
    assert len(second_page.items) == 1
