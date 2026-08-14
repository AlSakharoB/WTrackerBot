"""Persistence repositories."""

from app.repositories.diary import DiaryRepository
from app.repositories.dishes import DishRepository
from app.repositories.goals import GoalRepository
from app.repositories.ingredients import IngredientRepository
from app.repositories.search import SearchRepository
from app.repositories.users import UserRepository
from app.repositories.weights import WeightRepository

__all__ = [
    "DiaryRepository",
    "DishRepository",
    "GoalRepository",
    "IngredientRepository",
    "SearchRepository",
    "UserRepository",
    "WeightRepository",
]
