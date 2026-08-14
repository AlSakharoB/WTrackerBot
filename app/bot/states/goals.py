from aiogram.fsm.state import State, StatesGroup


class GoalCreateStates(StatesGroup):
    wait_target_weight = State()
    choose_target_date = State()
    wait_target_date = State()
    confirm = State()
