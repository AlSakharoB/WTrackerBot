from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from app.db.models.account_deletion import AccountDeletionRequest
from app.db.models.diary import DiaryEntry
from app.db.models.dish import Dish, DishIngredient
from app.db.models.goal import GoalStatus, WeightGoal
from app.db.models.ingredient import Ingredient
from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.reminder import ReminderSetting
from app.db.models.share import ShareImport, SharePackage
from app.db.models.ui_preference import UserUIPreference
from app.db.models.user import User
from app.db.models.web_mutation import WebMutationReceipt
from app.db.models.weight import WeightEntry
from app.user_settings import AfterFoodAddAction, NumberFormat


@dataclass(frozen=True, slots=True)
class PrivacyExportRecords:
    user: User
    ui_preferences: UserUIPreference | None
    ingredients: list[Ingredient]
    dishes: list[Dish]
    dish_ingredients: list[DishIngredient]
    diary_entries: list[DiaryEntry]
    weight_entries: list[WeightEntry]
    weight_goals: list[WeightGoal]
    nutrition_goals: list[NutritionGoal]
    reminders: list[ReminderSetting]
    share_packages: list[SharePackage]
    share_imports: list[ShareImport]


class PrivacyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def atomic(self) -> AbstractAsyncContextManager[AsyncSessionTransaction]:
        return self._session.begin_nested()

    async def counts(self, user_id: int) -> tuple[int, int, int, int, int, int, int]:
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
            select(func.count())
            .select_from(SharePackage)
            .where(SharePackage.owner_user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(ShareImport)
            .where(ShareImport.recipient_user_id == user_id)
            .scalar_subquery(),
        )
        ingredients, dishes, diary, weights, goals, shares, share_imports = (
            await self._session.execute(statement)
        ).one()
        return (
            int(ingredients),
            int(dishes),
            int(diary),
            int(weights),
            int(goals),
            int(shares),
            int(share_imports),
        )

    async def profile_stats(self, user_id: int) -> tuple[int, int, int, int]:
        statement = select(
            select(func.count(func.distinct(DiaryEntry.entry_date)))
            .where(DiaryEntry.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(Ingredient)
            .where(Ingredient.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(Dish)
            .where(Dish.user_id == user_id)
            .scalar_subquery(),
            select(func.count())
            .select_from(WeightEntry)
            .where(WeightEntry.user_id == user_id)
            .scalar_subquery(),
        )
        diary_days, ingredients, dishes, weights = (
            await self._session.execute(statement)
        ).one()
        return (
            int(diary_days),
            int(ingredients),
            int(dishes),
            int(weights),
        )

    async def export_records(self, user_id: int) -> PrivacyExportRecords | None:
        user = await self._session.scalar(select(User).where(User.id == user_id))
        if user is None:
            return None

        ingredients = list(
            (
                await self._session.scalars(
                    select(Ingredient).where(Ingredient.user_id == user_id)
                )
            ).all()
        )
        dishes = list(
            (
                await self._session.scalars(select(Dish).where(Dish.user_id == user_id))
            ).all()
        )
        dish_ids = [dish.id for dish in dishes]
        dish_ingredients = (
            list(
                (
                    await self._session.scalars(
                        select(DishIngredient).where(
                            DishIngredient.dish_id.in_(dish_ids)
                        )
                    )
                ).all()
            )
            if dish_ids
            else []
        )

        async def owned(model: type, owner_column: object) -> list:
            statement = select(model).where(owner_column == user_id)
            return list((await self._session.scalars(statement)).all())

        return PrivacyExportRecords(
            user=user,
            ui_preferences=await self._session.scalar(
                select(UserUIPreference).where(UserUIPreference.user_id == user_id)
            ),
            ingredients=ingredients,
            dishes=dishes,
            dish_ingredients=dish_ingredients,
            diary_entries=await owned(DiaryEntry, DiaryEntry.user_id),
            weight_entries=await owned(WeightEntry, WeightEntry.user_id),
            weight_goals=await owned(WeightGoal, WeightGoal.user_id),
            nutrition_goals=await owned(NutritionGoal, NutritionGoal.user_id),
            reminders=await owned(ReminderSetting, ReminderSetting.user_id),
            share_packages=await owned(SharePackage, SharePackage.owner_user_id),
            share_imports=await owned(ShareImport, ShareImport.recipient_user_id),
        )

    async def delete_share_imports(self, user_id: int) -> None:
        await self._session.execute(
            delete(ShareImport).where(ShareImport.recipient_user_id == user_id)
        )

    async def delete_share_packages(self, user_id: int) -> None:
        await self._session.execute(
            delete(SharePackage).where(SharePackage.owner_user_id == user_id)
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

    async def delete_web_state(self, user_id: int) -> None:
        await self._session.execute(
            delete(UserUIPreference).where(UserUIPreference.user_id == user_id)
        )
        await self._session.execute(
            delete(WebMutationReceipt).where(WebMutationReceipt.user_id == user_id)
        )
        await self._session.execute(
            delete(AccountDeletionRequest).where(
                AccountDeletionRequest.user_id == user_id
            )
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
                confirm_deletions=True,
            )
            .returning(User)
            .execution_options(populate_existing=True)
        )
        return await self._session.scalar(statement)
