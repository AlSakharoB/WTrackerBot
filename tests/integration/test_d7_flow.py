from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.goals import goal_card
from app.db.models.diary import MealType
from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.goals import GoalRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.nutrition_goals import NutritionGoalRepository
from app.repositories.privacy import PrivacyRepository
from app.repositories.search import SearchRepository
from app.repositories.users import UserRepository
from app.repositories.weights import WeightRepository
from app.services.diary import DiaryService
from app.services.dishes import DishComponentData, DishService
from app.services.goals import GoalService
from app.services.ingredients import CreateIngredientData, IngredientService
from app.services.privacy import PrivacyService, UserDataSummary
from app.services.search import SearchService
from app.services.settings import UserSettingsService
from app.services.users import TelegramUserData, UserService
from app.services.weights import WeightService
from app.user_settings import AfterFoodAddAction, NumberFormat


async def test_d7_new_user_full_flow(session: AsyncSession) -> None:
    user = (
        await UserService(
            UserRepository(session),
            default_timezone="Europe/Moscow",
        ).sync_telegram_user(
            TelegramUserData(
                telegram_id=9790000001,
                username="d7_user",
                first_name="D7",
                last_name="Flow",
                language_code="ru",
            )
        )
    ).user
    ingredient_repository = IngredientRepository(session)
    dish_repository = DishRepository(session)
    ingredient = await IngredientService(ingredient_repository).create(
        user.id,
        CreateIngredientData(
            name="Куриная грудка",
            kcal_per_100g=Decimal("165"),
            protein_per_100g=Decimal("31"),
            fat_per_100g=Decimal("3.6"),
            carbs_per_100g=Decimal("0"),
        ),
    )
    dish = await DishService(dish_repository).create(
        user.id,
        "Куриный ужин",
        [DishComponentData(ingredient.id, Decimal("200"))],
    )

    search = SearchService(SearchRepository(session))
    ingredient_results = await search.search_ingredients(user.id, "кур груд")
    dish_results = await search.search_dishes(user.id, "кур ужн")
    assert ingredient_results[0].entity_id == ingredient.id
    assert dish_results[0].entity_id == dish.dish.id

    diary = DiaryService(
        DiaryRepository(session),
        ingredient_repository,
        dish_repository,
        NutritionGoalRepository(session),
    )
    entry_date = date(2026, 8, 14)
    entry = await diary.add_dish(
        user_id=user.id,
        dish_id=dish.dish.id,
        grams=Decimal("200"),
        meal_type=MealType.DINNER,
        entry_date=entry_date,
    )
    assert entry.source_name == "Куриный ужин"

    weight_repository = WeightRepository(session)
    weights = WeightService(weight_repository)
    await weights.create(
        user_id=user.id,
        weight_kg=Decimal("90"),
        measured_at=datetime(2026, 8, 1, 8, tzinfo=UTC),
    )
    goals = GoalService(GoalRepository(session), weight_repository)
    await goals.create(
        user_id=user.id,
        target_weight_kg=Decimal("80"),
        target_date=None,
    )
    await weights.create(
        user_id=user.id,
        weight_kg=Decimal("85"),
        measured_at=datetime(2026, 8, 14, 8, tzinfo=UTC),
    )
    goal = await goals.get_active(user.id)
    assert goal is not None
    assert goal.progress is not None
    assert goal.progress.percentage == Decimal("50.0")
    assert "█████░░░░░ 50%" in goal_card(goal)

    settings = UserSettingsService(UserRepository(session))
    changed = await settings.set_timezone(user.id, "Asia/Almaty")
    changed = await settings.set_number_format(
        changed.id,
        NumberFormat.ONE_DECIMAL,
    )
    changed = await settings.set_after_food_add_action(
        changed.id,
        AfterFoodAddAction.STAY,
    )
    assert changed.timezone == "Asia/Almaty"
    assert changed.number_format == NumberFormat.ONE_DECIMAL.value
    assert changed.after_food_add_action == AfterFoodAddAction.STAY.value

    summary = await PrivacyService(
        PrivacyRepository(session),
        default_timezone="Europe/Moscow",
    ).summary(user.id)
    assert summary == UserDataSummary(
        ingredients=1,
        dishes=1,
        diary_entries=1,
        weight_entries=2,
        active_goals=1,
    )
