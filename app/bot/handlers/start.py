from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.sharing import handle_ingredient_share_start
from app.bot.keyboards.main import build_main_menu_keyboard
from app.db.models.user import User
from app.sharing.payloads import SharePayloadLimits

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
    db_session: AsyncSession | None = None,
    bot_username: str | None = None,
    share_link_ttl_days: int = 30,
    share_payload_limits: SharePayloadLimits | None = None,
) -> None:
    await state.clear()
    payload = extract_start_payload(message.text)
    if payload is not None and payload.startswith("sh_"):
        if db_session is None:  # pragma: no cover - dispatcher always injects it
            raise RuntimeError("Database session is required for share links")
        await handle_ingredient_share_start(
            message,
            state,
            current_user,
            db_session,
            payload,
            bot_username=bot_username,
            share_link_ttl_days=share_link_ttl_days,
            share_payload_limits=share_payload_limits or SharePayloadLimits(),
        )
        return
    text = WELCOME_TEXT if is_new_user else MENU_TEXT
    await message.answer(text, reply_markup=build_main_menu_keyboard())


def extract_start_payload(text: object) -> str | None:
    if not isinstance(text, str):
        return None
    parts = text.strip().split(maxsplit=1)
    if not parts or parts[0].split("@", maxsplit=1)[0].lower() != "/start":
        return None
    return parts[1].strip() if len(parts) == 2 else None


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
