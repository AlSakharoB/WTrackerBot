from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards.main import build_main_menu_keyboard
from app.db.models.user import User

router = Router(name=__name__)

WELCOME_TEXT = """Привет! 👋

Я помогу вести рацион, считать КБЖУ,
сохранять вес и отслеживать цель.

Для начала можно добавить продукты,
которые ты обычно используешь."""

MENU_TEXT = "Главное меню"


@router.message(CommandStart())
async def start_handler(
    message: Message,
    current_user: User,
    is_new_user: bool,
    state: FSMContext,
) -> None:
    await state.clear()
    text = WELCOME_TEXT if is_new_user else MENU_TEXT
    await message.answer(text, reply_markup=build_main_menu_keyboard())


@router.message(Command("menu"))
async def menu_handler(
    message: Message,
    current_user: User,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=build_main_menu_keyboard())


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    await state.clear()
    text = "Действие отменено." if current_state else "Нет активного действия."
    await message.answer(text, reply_markup=build_main_menu_keyboard())
