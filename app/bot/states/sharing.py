from aiogram.fsm.state import State, StatesGroup


class ShareImportStates(StatesGroup):
    preview = State()
    conflict = State()
    batch_preview = State()
    batch_conflict = State()
    dish_preview = State()
    dish_ingredient_conflict = State()
    dish_name_conflict = State()
    dish_batch_preview = State()
    dish_batch_ingredient_conflict = State()
    dish_batch_dish_plan = State()


class ShareIngredientSelectionStates(StatesGroup):
    selecting = State()
    wait_search_query = State()


class ShareDishSelectionStates(StatesGroup):
    selecting = State()
    wait_search_query = State()


class ShareManagementStates(StatesGroup):
    confirmation = State()
