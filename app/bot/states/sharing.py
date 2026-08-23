from aiogram.fsm.state import State, StatesGroup


class ShareImportStates(StatesGroup):
    preview = State()
    conflict = State()
    batch_preview = State()
    batch_conflict = State()


class ShareIngredientSelectionStates(StatesGroup):
    selecting = State()
    wait_search_query = State()
