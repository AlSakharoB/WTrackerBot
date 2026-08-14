from contextlib import AbstractAsyncContextManager

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.db.models.diary import DiaryEntry
from app.db.models.dish import Dish, DishIngredient
from app.db.models.goal import GoalStatus, WeightGoal
from app.db.models.ingredient import Ingredient
from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.reminder import ReminderSetting
from app.db.models.user import User
from app.db.models.weight import WeightEntry
from app.user_settings import AfterFoodAddAction, NumberFormat


class PrivacyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def atomic(self) -> AbstractAsyncContextManager[AsyncSessionTransaction]:
        return self._session.begin_nested()

    async def counts(self, user_id: int) -> tuple[int, int, int, int, int]:
        statement = select(
            select(func.count())
            .select_from(Ingredient)
            .where(Ingredient.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(Dish)
            .where(Dish.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(DiaryEntry)
            .where(DiaryEntry.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(WeightGoal)
            .where(
                WeightGoal.user_id == user_id,
                WeightGoal.status == GoalStatus.ACTIVE,
            )
            .scalar_subquery(),
        )
        ingredients, dishes, diary, weights, goals = (
            await self._session.execute(statement)
        ).one()
        return (
            int(ingredients),
            int(dishes),
            int(diary),
            int(weights),
            int(goals),
        )

    async def delete_diary_entries(self, user_id: int) -> None:
        await self._session.execute(
            delete(DiaryEntry).where(DiaryEntry.user_id == user_id)
        )

    async def delete_dish_ingredients(self, user_id: int) -> None:
        dish_ids = select(Dish.id).where(Dish.user_id == user_id)
        await self._session.execute(
            delete(DishIngredient).where(DishIngredient.dish_id.in_(dish_ids))
        )

    async def delete_dishes(self, user_id: int) -> None:
        await self._session.execute(delete(Dish).where(Dish.user_id == user_id))

    async def delete_ingredients(self, user_id: int) -> None:
        await self._session.execute(
            delete(Ingredient).where(Ingredient.user_id == user_id)
        )

    async def delete_weight_entries(self, user_id: int) -> None:
        await self._session.execute(
            delete(WeightEntry).where(WeightEntry.user_id == user_id)
        )

    async def delete_weight_goals(self, user_id: int) -> None:
        await self._session.execute(
            delete(WeightGoal).where(WeightGoal.user_id == user_id)
        )

    async def delete_nutrition_goals(self, user_id: int) -> None:
        await self._session.execute(
            delete(NutritionGoal).where(NutritionGoal.user_id == user_id)
        )

    async def delete_reminder_settings(self, user_id: int) -> None:
        await self._session.execute(
            delete(ReminderSetting).where(ReminderSetting.user_id == user_id)
        )

    async def reset_preferences(
        self,
        user_id: int,
        *,
        default_timezone: str,
    ) -> User | None:
        statement = (
            update(User)
            .where(User.id == user_id)
            .values(
                timezone=default_timezone,
                number_format=NumberFormat.AUTOMATIC.value,
                after_food_add_action=AfterFoodAddAction.OPEN_TODAY.value,
            )
            .returning(User)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)
