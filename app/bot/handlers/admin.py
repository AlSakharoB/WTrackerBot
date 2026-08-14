import logging
from datetime import UTC
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.admin import (
    AdminAction,
    AdminCallback,
    build_admin_back_keyboard,
    build_admin_menu_keyboard,
)
from app.core.health import HealthService, format_health_report
from app.repositories.admin import AdminRepository
from app.services.admin_notifications import AdminNotificationService

router = Router(name=__name__)
logger = logging.getLogger(__name__)

ADMIN_MENU_TEXT = """🛠 <b>Админ-панель</b>

Выберите раздел:"""
ACCESS_DENIED_TEXT = "Доступ запрещён."


def _is_admin(telegram_id: int, admin_telegram_ids: set[int]) -> bool:
    return telegram_id in admin_telegram_ids


async def _deny_message(message: Message) -> None:
    logger.warning(
        "Admin section access denied",
        extra={"operation": "admin.access_denied"},
    )
    await message.answer(ACCESS_DENIED_TEXT)


async def _deny_callback(callback: CallbackQuery) -> None:
    logger.warning(
        "Admin callback access denied",
        extra={"operation": "admin.callback.access_denied"},
    )
    await callback.answer(ACCESS_DENIED_TEXT, show_alert=True)


async def _edit_admin_screen(
    callback: CallbackQuery,
    text: str,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=build_admin_back_keyboard(),
        )


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    state: FSMContext,
    admin_telegram_ids: set[int],
) -> None:
    if not _is_admin(message.from_user.id, admin_telegram_ids):
        await _deny_message(message)
        return

    await state.clear()
    logger.info(
        "Admin action",
        extra={"operation": "admin.open", "user_id": message.from_user.id},
    )
    await message.answer(ADMIN_MENU_TEXT, reply_markup=build_admin_menu_keyboard())


@router.callback_query(AdminCallback.filter())
async def admin_callback(
    callback: CallbackQuery,
    callback_data: AdminCallback,
    admin_telegram_ids: set[int],
    db_session: AsyncSession,
    health_service: HealthService,
    admin_notification_service: AdminNotificationService,
    app_environment: str,
    app_version: str,
    git_commit_sha: str,
) -> None:
    if not _is_admin(callback.from_user.id, admin_telegram_ids):
        await _deny_callback(callback)
        return

    action = callback_data.action
    logger.info(
        "Admin action",
        extra={
            "operation": f"admin.{action.value}",
            "user_id": callback.from_user.id,
        },
    )

    if action is AdminAction.CLOSE:
        await callback.answer()
        if callback.message is not None:
            await callback.message.delete()
        return
    if action is AdminAction.MENU:
        await callback.answer()
        if callback.message is not None:
            await callback.message.edit_text(
                ADMIN_MENU_TEXT,
                reply_markup=build_admin_menu_keyboard(),
            )
        return
    if action is AdminAction.HEALTH:
        report = await health_service.get_full_health()
        await _edit_admin_screen(callback, format_health_report(report))
        return

    repository = AdminRepository(db_session)
    if action is AdminAction.USERS:
        stats = await repository.get_user_stats()
        text = f"""👥 <b>Пользователи</b>

Всего пользователей: {stats.total}
Новых сегодня: {stats.new_today}
Новых за 7 дней: {stats.new_last_7_days}"""
    elif action is AdminAction.STATS:
        stats = await repository.get_entity_stats()
        text = f"""📊 <b>Статистика</b>

Ингредиенты: {stats.ingredients}
Блюда: {stats.dishes}
Записи питания: {stats.diary_entries}
Записи веса: {stats.weight_entries}
Активные цели веса: {stats.active_weight_goals}"""
    elif action is AdminAction.DATABASE:
        info = await repository.get_database_info()
        revision = await health_service.check_database_revision()
        text = f"""🗄 <b>База данных</b>

PostgreSQL: {escape(info.postgresql_version)}
Размер: {escape(info.database_size)}
Current revision: {escape(revision.details.get("current", "unknown"))}
Expected head: {escape(revision.details.get("expected", "unknown"))}
Статус: {revision.message.upper()}"""
    elif action is AdminAction.VERSION:
        started_at = health_service.started_at
        uptime = health_service.uptime_seconds
        text = f"""⚙️ <b>Версия приложения</b>

App version: {escape(app_version)}
Commit SHA: {escape(git_commit_sha)}
Environment: {escape(app_environment)}
Started at: {started_at:%d.%m.%Y %H:%M} UTC
Uptime: {_format_uptime(uptime)}"""
    else:
        stats = admin_notification_service.stats
        last_error = (
            stats.last_error_at.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
            if stats.last_error_at is not None
            else "нет"
        )
        text = f"""❗ <b>Ошибки</b>

Ошибок за runtime: {stats.total_errors}
Подавлено уведомлений: {stats.suppressed_notifications}
Последняя ошибка: {last_error}
Последний fingerprint: {escape(stats.last_fingerprint or "нет")}"""

    await _edit_admin_screen(callback, text)


def _format_uptime(seconds: int) -> str:
    days, remainder = divmod(max(0, seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {seconds}s"
