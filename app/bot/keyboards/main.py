from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

TODAY_BUTTON = "📅 Сегодня"
ADD_FOOD_BUTTON = "➕ Добавить еду"
INGREDIENTS_BUTTON = "🥕 Ингредиенты"
DISHES_BUTTON = "🍲 Блюда"
WEIGHT_BUTTON = "⚖️ Вес"
GOAL_BUTTON = "🎯 Цель"
SETTINGS_BUTTON = "⚙️ Настройки"
HELP_BUTTON = "❓ Помощь"


def build_main_menu_keyboard(
    *,
    miniapp_url: str | None = None,
    miniapp_button_text: str = "Открыть дневник",
) -> ReplyKeyboardMarkup:
    keyboard = [
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
    ]
    if miniapp_url is not None:
        keyboard.append(
            [
                KeyboardButton(
                    text=miniapp_button_text,
                    web_app=WebAppInfo(url=miniapp_url),
                )
            ]
        )
    keyboard.append([KeyboardButton(text=HELP_BUTTON)])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел",
    )
