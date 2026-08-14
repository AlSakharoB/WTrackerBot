from aiogram import Bot
from aiogram.types import BotCommand

BOT_COMMANDS = [
    BotCommand(command="start", description="Запустить бота"),
    BotCommand(command="menu", description="Открыть главное меню"),
    BotCommand(command="ingredients", description="Открыть ингредиенты"),
    BotCommand(command="dishes", description="Открыть блюда"),
    BotCommand(command="today", description="Открыть рацион за сегодня"),
    BotCommand(command="addfood", description="Добавить еду в рацион"),
    BotCommand(command="weight", description="Открыть историю веса"),
    BotCommand(command="goal", description="Открыть цель по весу"),
    BotCommand(command="help", description="Показать помощь"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(BOT_COMMANDS)
