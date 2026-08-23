"""Telegram update handlers."""

from aiogram import Router

from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import (
    global_error_handler,
)
from app.bot.handlers.common import (
    router as common_router,
)
from app.bot.handlers.diary import router as diary_router
from app.bot.handlers.dishes import router as dishes_router
from app.bot.handlers.goals import router as goals_router
from app.bot.handlers.ingredients import router as ingredients_router
from app.bot.handlers.reminders import router as reminders_router
from app.bot.handlers.settings import router as settings_router
from app.bot.handlers.sharing import router as sharing_router
from app.bot.handlers.sharing_batch import router as sharing_batch_router
from app.bot.handlers.start import router as start_router
from app.bot.handlers.weight_chart import router as weight_chart_router
from app.bot.handlers.weights import router as weights_router


def build_root_router() -> Router:
    router = Router(name="root")
    router.errors.register(global_error_handler)
    router.include_router(admin_router)
    router.include_router(start_router)
    router.include_router(sharing_router)
    router.include_router(sharing_batch_router)
    router.include_router(ingredients_router)
    router.include_router(dishes_router)
    router.include_router(diary_router)
    router.include_router(weights_router)
    router.include_router(weight_chart_router)
    router.include_router(goals_router)
    router.include_router(reminders_router)
    router.include_router(settings_router)
    router.include_router(common_router)
    return router
