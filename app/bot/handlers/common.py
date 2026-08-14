import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ErrorEvent, Message

from app.bot.keyboards.main import (
    HELP_BUTTON,
    build_main_menu_keyboard,
)
from app.exceptions import AppError
from app.services.admin_notifications import AdminNotificationService

router = Router(name=__name__)
logger = logging.getLogger(__name__)

HELP_TEXT = """<b>Что умеет бот:</b>

🥕 <b>Ингредиенты</b>
Создавайте продукты и указывайте КБЖУ на 100 г.

🍲 <b>Блюда</b>
Собирайте рецепты из ингредиентов. КБЖУ считается автоматически.

📅 <b>Рацион</b>
Добавляйте еду за день и смотрите итоговые КБЖУ.

⚖️ <b>Вес</b>
Сохраняйте измерения веса с датой и временем.

🎯 <b>Цель</b>
Укажите целевой вес и при желании срок.

Во время ввода отправьте /cancel, чтобы отменить действие."""

FALLBACK_TEXT = "Не удалось распознать команду. Выберите раздел в меню или /help."


def _error_log_context(event: ErrorEvent) -> dict[str, object]:
    update = event.update
    message = update.message
    callback = update.callback_query
    telegram_user = None
    operation = "telegram.unknown"
    if callback is not None:
        telegram_user = getattr(callback, "from_user", None)
        operation = "telegram.callback_query"
    elif message is not None:
        telegram_user = getattr(message, "from_user", None)
        operation = "telegram.message"

    handler = "unknown"
    traceback = event.exception.__traceback__
    while traceback is not None:
        module_name = traceback.tb_frame.f_globals.get("__name__", "")
        if module_name.startswith("app.bot.handlers."):
            handler = f"{module_name}.{traceback.tb_frame.f_code.co_name}"
        traceback = traceback.tb_next

    if handler != "unknown":
        operation = handler.removeprefix("app.bot.handlers.")

    return {
        "correlation_id": f"tg-{update.update_id}",
        "user_id": getattr(telegram_user, "id", None) or "-",
        "handler": handler,
        "operation": operation,
        "exception_type": type(event.exception).__name__,
    }


@router.message(Command("help"))
@router.message(F.text == HELP_BUTTON)
async def help_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(HELP_TEXT, reply_markup=build_main_menu_keyboard())


@router.message()
async def message_fallback_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    text = (
        "Ожидаю данные для текущего действия. Следуйте подсказке или отправьте /cancel."
        if current_state
        else FALLBACK_TEXT
    )
    await message.answer(text, reply_markup=build_main_menu_keyboard())


@router.callback_query()
async def callback_fallback_handler(callback: CallbackQuery) -> None:
    logger.warning(
        "Invalid or stale callback data",
        extra={"operation": "telegram.callback.invalid"},
    )
    await callback.answer(
        "Кнопка устарела. Откройте раздел заново.",
        show_alert=True,
    )


async def global_error_handler(
    event: ErrorEvent,
    admin_notification_service: AdminNotificationService | None = None,
) -> bool:
    exception = event.exception
    log_context = _error_log_context(event)
    if isinstance(exception, AppError):
        logger.warning(
            "Unhandled domain error: %s",
            type(exception).__name__,
            extra=log_context,
        )
        text = str(exception)
    else:
        logger.exception(
            "Unhandled handler exception",
            exc_info=(type(exception), exception, exception.__traceback__),
            extra=log_context,
        )
        if admin_notification_service is not None:
            await admin_notification_service.notify_error(
                exception,
                correlation_id=str(log_context["correlation_id"]),
                operation=str(log_context["operation"]),
                user_id=(
                    log_context["user_id"]
                    if isinstance(log_context["user_id"], int)
                    else None
                ),
            )
        text = "Произошла внутренняя ошибка. Повторите действие позже."

    message = event.update.message
    callback = event.update.callback_query
    try:
        if callback is not None:
            await callback.answer(text, show_alert=True)
        elif message is not None:
            await message.answer(
                escape(text),
                reply_markup=build_main_menu_keyboard(),
            )
    except Exception:
        logger.exception(
            "Failed to notify user about update error",
            extra=log_context,
        )
    return True
