from aiogram.filters.callback_data import CallbackData

INGREDIENT_SAVE_ACTION = "ingredient_save"
DISH_SAVE_ACTION = "dish_save"
DIARY_SAVE_ACTION = "diary_save"
WEIGHT_SAVE_ACTION = "weight_save"
GOAL_SAVE_ACTION = "goal_save"
NUTRITION_GOAL_TODAY_ACTION = "nutrition_today"
NUTRITION_GOAL_TOMORROW_ACTION = "nutrition_tomorrow"


class ConfirmActionCallback(CallbackData, prefix="confirm"):
    action: str
    token: str
