from typing import Any

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.services.action_lock import action_token_matches

STALE_ACTION_TEXT = "Кнопка устарела. Откройте раздел заново."


async def confirmation_data(
    callback: CallbackQuery,
    state: FSMContext,
    action_token: str,
) -> dict[str, Any] | None:
    data = await state.get_data()
    if action_token_matches(data.get("action_token"), action_token):
        return data
    await callback.answer(STALE_ACTION_TEXT, show_alert=True)
    return None
