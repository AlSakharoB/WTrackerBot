from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

TODAY_BUTTON = "📅 Сегодня"
ADD_FOOD_BUTTON = "➕ Добавить еду"
INGREDIENTS_BUTTON = "🥕 Ингредиенты"
DISHES_BUTTON = "🍲 Блюда"
WEIGHT_BUTTON = "⚖️ Вес"
GOAL_BUTTON = "🎯 Цель"
SETTINGS_BUTTON = "⚙️ Настройки"
HELP_BUTTON = "❓ Помощь"


def build_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TODAY_BUTTON)],
            [
                KeyboardButton(text=ADD_FOOD_BUTTON),
                KeyboardButton(text=INGREDIENTS_BUTTON),
            ],
            [
                KeyboardButton(text=DISHES_BUTTON),
                KeyboardButton(text=WEIGHT_BUTTON),
            ],
            [
                KeyboardButton(text=GOAL_BUTTON),
                KeyboardButton(text=SETTINGS_BUTTON),
            ],
            [KeyboardButton(text=HELP_BUTTON)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел",
    )
