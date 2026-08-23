from aiogram.fsm.state import State, StatesGroup


class ShareImportStates(StatesGroup):
    preview = State()
    conflict = State()
