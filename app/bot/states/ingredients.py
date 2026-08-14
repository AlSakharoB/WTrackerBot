from aiogram.fsm.state import State, StatesGroup


class IngredientCreateStates(StatesGroup):
    wait_name = State()
    wait_kcal = State()
    wait_protein = State()
    wait_fat = State()
    wait_carbs = State()
    confirm = State()


class IngredientSearchStates(StatesGroup):
    wait_query = State()


class IngredientEditStates(StatesGroup):
    wait_value = State()
