from aiogram.fsm.state import State, StatesGroup


class DiaryAddStates(StatesGroup):
    wait_grams = State()
    choose_meal = State()
    choose_date = State()
    wait_date = State()
    confirm = State()


class DiaryDateStates(StatesGroup):
    wait_date = State()


class DiaryEditStates(StatesGroup):
    wait_grams = State()
    wait_date = State()
