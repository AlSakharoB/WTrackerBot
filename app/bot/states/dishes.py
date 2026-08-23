from aiogram.fsm.state import State, StatesGroup


class DishEditorStates(StatesGroup):
    wait_name = State()
    editor = State()
    wait_ingredient_search = State()
    wait_ingredient_grams = State()


class DishSearchStates(StatesGroup):
    wait_query = State()
