from aiogram.fsm.state import State, StatesGroup


class WeightAddStates(StatesGroup):
    wait_weight = State()
    choose_time = State()
    wait_datetime = State()
    confirm = State()


class WeightEditStates(StatesGroup):
    wait_weight = State()
    wait_datetime = State()


class WeightChartStates(StatesGroup):
    wait_date_from = State()
    wait_date_to = State()
