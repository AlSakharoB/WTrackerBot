from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dishes import DishRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.repositories.users import UserRepository
from app.services.dishes import DishComponentData, DishService
from app.services.ingredients import CreateIngredientData, IngredientService
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
            first_name="Search Test",
            last_name=None,
            language_code="ru",
        )
    )
    return result.user.id


async def create_ingredient(
    session: AsyncSession,
    user_id: int,
    name: str,
) -> int:
    ingredient = await IngredientService(IngredientRepository(session)).create(
        user_id,
        CreateIngredientData(
            name=name,
            kcal_per_100g=Decimal("100"),
            protein_per_100g=Decimal("10"),
            fat_per_100g=Decimal("5"),
            carbs_per_100g=Decimal("15"),
        ),
    )
    return ingredient.id


async def test_ingredient_fuzzy_search_relevance_and_isolation(
    session: AsyncSession,
) -> None:
    owner_id = await create_user(session, 9440000001)
    other_id = await create_user(session, 9440000002)
    owner_names = [
        "Яичный белок",
        "Яичный салат",
        "Куриная грудка",
        "Куриное филе",
        "Гречка вареная",
        "Творог",
        "Творожный продукт",
        "Оливковое масло",
        "Ёжевика",
    ]
    for name in owner_names:
        await create_ingredient(session, owner_id, name)
    foreign_id = await create_ingredient(session, other_id, "Яиный чужой")
    service = SearchService(SearchRepository(session))

    expected_queries = {
        "яичный": "Яичный белок",
        "яиный": "Яичный белок",
        "яичн": "Яичный белок",
        "кур": "Куриная грудка",
        "кур груд": "Куриная грудка",
        "греч вар": "Гречка вареная",
        "тварог": "Творог",
        "ОЛИВКОВОЕ": "Оливковое масло",
        "  кур   груд  ": "Куриная грудка",
        "ежевика": "Ёжевика",
    }
    query_results = {
        query: await service.search_ingredients(owner_id, query)
        for query in expected_queries
    }
    exact_results = await service.search_ingredients(owner_id, "Творог")

    assert {result.name for result in query_results["яиный"]} >= {
        "Яичный белок",
        "Яичный салат",
    }
    for query, expected_name in expected_queries.items():
        results = query_results[query]
        assert expected_name in {result.name for result in results}
        assert all(result.entity_id != foreign_id for result in results)
        assert len(results) <= 10
    assert exact_results[0].name == "Творог"
    assert exact_results[0].score > exact_results[1].score

    for index in range(12):
        await create_ingredient(session, owner_id, f"Продукт тестовый {index}")
    limited_results = await service.search_ingredients(owner_id, "продукт")
    assert len(limited_results) == 10


async def test_dish_search_uses_same_fuzzy_core(session: AsyncSession) -> None:
    owner_id = await create_user(session, 9440000003)
    other_id = await create_user(session, 9440000004)
    owner_ingredient_id = await create_ingredient(session, owner_id, "Яйцо")
    other_ingredient_id = await create_ingredient(session, other_id, "Яйцо")
    owner_service = DishService(DishRepository(session))
    other_service = DishService(DishRepository(session))

    omelet = await owner_service.create(
        owner_id,
        "Яичный омлет",
        [DishComponentData(owner_ingredient_id, Decimal("100"))],
    )
    await owner_service.create(
        owner_id,
        "Курица с гречкой",
        [DishComponentData(owner_ingredient_id, Decimal("50"))],
    )
    await owner_service.create(
        owner_id,
        "Творожная запеканка",
        [DishComponentData(owner_ingredient_id, Decimal("70"))],
    )
    foreign = await other_service.create(
        other_id,
        "Яиный омлет чужой",
        [DishComponentData(other_ingredient_id, Decimal("100"))],
    )
    service = SearchService(SearchRepository(session))

    expected_queries = {
        "яиный омл": "Яичный омлет",
        "яичн": "Яичный омлет",
        "КУР ГРЕЧ": "Курица с гречкой",
        "  кур   греч  ": "Курица с гречкой",
        "творож зап": "Творожная запеканка",
    }
    query_results = {
        query: await service.search_dishes(owner_id, query)
        for query in expected_queries
    }

    assert query_results["яиный омл"][0].entity_id == omelet.dish.id
    for query, expected_name in expected_queries.items():
        results = query_results[query]
        assert expected_name in {result.name for result in results}
        assert all(result.entity_id != foreign.dish.id for result in results)
        assert len(results) <= 10

    for index in range(12):
        await owner_service.create(
            owner_id,
            f"Блюдо тестовое {index}",
            [DishComponentData(owner_ingredient_id, Decimal("10"))],
        )
    limited_results = await service.search_dishes(owner_id, "блюдо")
    assert len(limited_results) == 10
