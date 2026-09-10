"""SQLAlchemy model package."""

from app.db.models.account_deletion import AccountDeletionRequest
from app.db.models.diary import DiaryEntry, DiaryEntryType, MealType
from app.db.models.dish import Dish, DishIngredient
from app.db.models.food_folder import FoodFolder, FoodFolderItem
from app.db.models.goal import GoalStatus, WeightGoal
from app.db.models.ingredient import Ingredient
from app.db.models.nutrition_goal import NutritionGoal
from app.db.models.reminder import ReminderSetting, ReminderType
from app.db.models.share import (
    ShareImport,
    ShareImportStatus,
    SharePackage,
    SharePackageStatus,
    SharePackageType,
)
from app.db.models.ui_preference import UserUIPreference
from app.db.models.user import User
from app.db.models.web_mutation import WebMutationReceipt
from app.db.models.weight import WeightEntry

__all__ = [
    "AccountDeletionRequest",
    "DiaryEntry",
    "DiaryEntryType",
    "Dish",
    "DishIngredient",
    "FoodFolder",
    "FoodFolderItem",
    "GoalStatus",
    "Ingredient",
    "MealType",
    "NutritionGoal",
    "ReminderSetting",
    "ReminderType",
    "ShareImport",
    "ShareImportStatus",
    "SharePackage",
    "SharePackageStatus",
    "SharePackageType",
    "User",
    "UserUIPreference",
    "WeightEntry",
    "WeightGoal",
    "WebMutationReceipt",
]
