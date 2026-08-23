import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError

from app.bot.commands import set_bot_commands
from app.bot.handlers import build_root_router
from app.bot.middlewares.action_lock import ActionLockMiddleware
from app.bot.middlewares.correlation import CorrelationIdMiddleware
from app.bot.middlewares.lifecycle import LifecycleMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.middlewares.user import UserMiddleware
from app.config import Settings, get_settings
from app.core.health import (
    HealthService,
    HealthState,
    ensure_database_revision_current,
    run_app_heartbeat,
)
from app.core.lifecycle import LifecycleManager
from app.core.logging import flush_logging_handlers, setup_logging
from app.db.session import (
    check_database_connection,
    create_database_engine,
    create_session_factory,
)
from app.services.action_lock import ActionLockService
from app.services.admin_notifications import AdminNotificationService
from app.services.rate_limit import RateLimitRule, RateLimitScope, RateLimitService
from app.services.reminder_scheduler import ReminderScheduler
from app.sharing.links import normalize_bot_username
from app.sharing.payloads import SharePayloadLimits

logger = logging.getLogger(__name__)


def create_dispatcher(settings: Settings) -> Dispatcher:
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    lifecycle = LifecycleManager(
        drain_timeout_seconds=settings.shutdown_drain_timeout_seconds
    )
    dispatcher = Dispatcher(
        database_engine=engine,
        lifecycle_manager=lifecycle,
        app_environment=settings.app_environment,
        app_version=settings.app_version,
        git_commit_sha=settings.git_commit_sha,
        admin_telegram_ids=settings.admin_telegram_ids,
        default_timezone=settings.default_timezone,
        bot_username=None,
        share_link_ttl_days=settings.share_link_ttl_days,
        share_payload_limits=SharePayloadLimits(
            max_items=settings.share_max_items,
            max_ingredients=settings.share_max_ingredients,
            max_components=settings.share_max_components,
            max_payload_bytes=settings.share_max_payload_bytes,
        ),
    )
    dispatcher["database_session_factory"] = session_factory
    lifecycle_middleware = LifecycleMiddleware(lifecycle)
    dispatcher.update.outer_middleware(lifecycle_middleware)
    # Drain must wrap error handling, and it must complete before FSM storage closes.
    dispatcher.update.outer_middleware._middlewares.insert(  # noqa: SLF001
        0,
        dispatcher.update.outer_middleware._middlewares.pop(),  # noqa: SLF001
    )
    dispatcher.update.outer_middleware(CorrelationIdMiddleware())
    rate_limit_service = RateLimitService(
        {
            RateLimitScope.MESSAGES: RateLimitRule(
                settings.rate_limit_messages_count,
                settings.rate_limit_messages_window_seconds,
            ),
            RateLimitScope.CALLBACKS: RateLimitRule(
                settings.rate_limit_callbacks_count,
                settings.rate_limit_callbacks_window_seconds,
            ),
            RateLimitScope.SEARCH: RateLimitRule(
                settings.rate_limit_search_count,
                settings.rate_limit_search_window_seconds,
            ),
            RateLimitScope.WEIGHT_CHART: RateLimitRule(
                settings.rate_limit_weight_chart_count,
                settings.rate_limit_weight_chart_window_seconds,
            ),
        },
        notice_cooldown_seconds=settings.rate_limit_notice_cooldown_seconds,
    )
    dispatcher["rate_limit_service"] = rate_limit_service
    dispatcher.update.outer_middleware(RateLimitMiddleware(rate_limit_service))
    action_lock_service = ActionLockService(settings.action_lock_ttl_seconds)
    dispatcher["action_lock_service"] = action_lock_service
    dispatcher.update.outer_middleware(ActionLockMiddleware(action_lock_service))
    dispatcher.update.outer_middleware(
        UserMiddleware(
            session_factory,
            default_timezone=settings.default_timezone,
        )
    )
    dispatcher.shutdown.register(lifecycle.shutdown)
    dispatcher.shutdown.handlers.insert(0, dispatcher.shutdown.handlers.pop())
    dispatcher.include_router(build_root_router())
    return dispatcher


async def run_bot(settings: Settings) -> None:
    logger.info("Application startup", extra={"operation": "lifecycle.startup"})
    dispatcher = create_dispatcher(settings)
    engine = dispatcher["database_engine"]
    lifecycle = dispatcher["lifecycle_manager"]
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    health_state = HealthState()
    admin_notifications = AdminNotificationService(
        bot,
        settings.admin_telegram_ids,
        cooldown_seconds=settings.admin_error_cooldown_seconds,
        max_per_minute=settings.admin_error_max_per_minute,
    )
    dispatcher["admin_notification_service"] = admin_notifications

    try:
        try:
            await check_database_connection(engine)
        except Exception as error:
            logger.exception("Database connection failed")
            await admin_notifications.notify_error(
                error,
                correlation_id=None,
                operation="database.connect",
                user_id=None,
            )
            raise
        logger.info(
            "Database connection established",
            extra={"operation": "database.connect"},
        )
        try:
            revision = await ensure_database_revision_current(engine)
        except Exception as error:
            logger.critical(
                "Database revision guard blocked application startup",
                exc_info=True,
                extra={"operation": "database.revision_guard"},
            )
            await admin_notifications.notify_error(
                error,
                correlation_id=None,
                operation="database.revision_guard",
                user_id=None,
            )
            raise
        logger.info(
            "Database revision is up to date: %s",
            ",".join(revision.current),
            extra={"operation": "database.revision_guard"},
        )
        try:
            bot_profile = await bot.get_me()
            if bot_profile.username is None:
                raise ValueError("Telegram bot profile has no username")
            dispatcher["bot_username"] = normalize_bot_username(bot_profile.username)
        except (TelegramAPIError, ValueError):
            logger.warning(
                "Failed to cache bot username; sharing links are unavailable",
                exc_info=True,
                extra={"operation": "telegram.bot_identity"},
            )
        reminder_scheduler = ReminderScheduler(
            bot,
            dispatcher["database_session_factory"],
            misfire_grace_seconds=settings.reminder_misfire_grace_seconds,
        )
        dispatcher["reminder_scheduler"] = reminder_scheduler
        lifecycle.register_shutdown_callback(
            "reminder_scheduler",
            reminder_scheduler.shutdown,
        )
        await reminder_scheduler.start()
        health_service = HealthService(
            engine,
            bot,
            health_state,
            heartbeat_stale_after_seconds=(
                settings.health_heartbeat_interval_seconds * 3
            ),
            scheduler=reminder_scheduler,
        )
        dispatcher["health_service"] = health_service
        heartbeat_task = asyncio.create_task(
            run_app_heartbeat(
                health_state,
                settings.health_heartbeat_interval_seconds,
            ),
            name="app-heartbeat",
        )
        lifecycle.register_background_task(heartbeat_task)
        logger.info(
            "App heartbeat started",
            extra={"operation": "health.heartbeat"},
        )
        try:
            await set_bot_commands(bot)
        except TelegramAPIError:
            logger.warning(
                "Failed to register Telegram commands; polling will continue",
                exc_info=True,
            )
        logger.info(
            "Bot polling started",
            extra={"operation": "telegram.polling"},
        )
        try:
            await dispatcher.start_polling(
                bot,
                close_bot_session=False,
                handle_signals=True,
            )
        except TelegramAPIError as error:
            logger.exception("Telegram API error stopped polling")
            await admin_notifications.notify_error(
                error,
                correlation_id=None,
                operation="telegram.polling",
                user_id=None,
            )
            raise
        except Exception as error:
            logger.exception("Unexpected error stopped polling")
            await admin_notifications.notify_error(
                error,
                correlation_id=None,
                operation="telegram.polling",
                user_id=None,
            )
            raise
    finally:
        logger.info(
            "Bot polling stopped",
            extra={"operation": "telegram.polling"},
        )
        try:
            await lifecycle.shutdown()
        finally:
            try:
                await bot.session.close()
            except Exception:
                logger.exception(
                    "Failed to close Telegram HTTP client",
                    extra={"operation": "lifecycle.close_telegram"},
                )
            try:
                await engine.dispose()
            except Exception:
                logger.exception(
                    "Failed to dispose database engine",
                    extra={"operation": "lifecycle.close_database"},
                )
            finally:
                logger.info(
                    "Application shutdown",
                    extra={"operation": "lifecycle.shutdown"},
                )
                flush_logging_handlers()


def main() -> None:
    settings = get_settings()
    setup_logging(settings)
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()
