from aiogram.fsm.state import State, StatesGroup


class SettingsDeleteStates(StatesGroup):
    wait_phrase = State()


class NutritionGoalStates(StatesGroup):
    wait_kcal = State()
    wait_protein = State()
    wait_fat = State()
    wait_carbs = State()
    choose_date = State()


class ReminderStates(StatesGroup):
    choose_weekdays = State()
    wait_time = State()
