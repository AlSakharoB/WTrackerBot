import asyncio
import logging
from pathlib import Path
from time import time

from aiogram import Bot

from app.config import get_settings
from app.core.logging import setup_logging
from app.services.admin_notifications import AdminNotificationService

logger = logging.getLogger(__name__)
MIGRATION_ALERT_MARKER = Path("/tmp/nutrition-bot-migration-alert")


def _marker_is_fresh(cooldown_seconds: int) -> bool:
    try:
        return time() - MIGRATION_ALERT_MARKER.stat().st_mtime < cooldown_seconds
    except OSError:
        return False


def _touch_marker() -> None:
    MIGRATION_ALERT_MARKER.touch(exist_ok=True)


async def notify_migration_failure() -> None:
    settings = get_settings()
    setup_logging(settings)
    if not settings.admin_telegram_ids:
        return
    if _marker_is_fresh(settings.admin_error_cooldown_seconds):
        return
    try:
        _touch_marker()
    except OSError as error:
        logger.error(
            "Failed to update migration alert cooldown marker",
            extra={
                "operation": "admin_notifications.startup",
                "exception_type": type(error).__name__,
            },
        )

    bot = Bot(token=settings.bot_token.get_secret_value())
    service = AdminNotificationService(
        bot,
        settings.admin_telegram_ids,
        cooldown_seconds=settings.admin_error_cooldown_seconds,
        max_per_minute=settings.admin_error_max_per_minute,
    )
    try:
        await service.notify_error(
            RuntimeError("migration failed"),
            correlation_id=None,
            operation="database.migration",
            user_id=None,
        )
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(notify_migration_failure())
    except Exception as error:
        logger.error(
            "Failed to run migration failure notifier",
            extra={
                "operation": "admin_notifications.startup",
                "exception_type": type(error).__name__,
            },
        )


if __name__ == "__main__":
    main()
