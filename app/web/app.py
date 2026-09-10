import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db.session import create_database_engine, create_session_factory
from app.integrations.open_food_facts import OpenFoodFactsClient
from app.services.barcodes import BarcodeConfirmationSigner, BarcodeRateLimiter
from app.services.web_mutations import run_web_mutation_receipt_cleanup
from app.web.auth import TelegramInitDataValidator
from app.web.errors import register_error_handlers
from app.web.middleware import (
    CorrelationIdMiddleware,
    RequestLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.web.routes import router


def create_web_app(
    settings: Settings | None = None,
    *,
    engine: AsyncEngine | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_engine = engine or create_database_engine(resolved_settings.database_url)
    resolved_session_factory = session_factory or create_session_factory(
        resolved_engine
    )
    owns_engine = engine is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cleanup_task = asyncio.create_task(
            run_web_mutation_receipt_cleanup(
                app.state.database_session_factory,
                interval_seconds=(
                    resolved_settings.web_mutation_receipt_cleanup_seconds
                ),
            ),
            name="web-mutation-receipt-cleanup",
        )
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await app.state.open_food_facts_client.aclose()
            if owns_engine:
                await app.state.database_engine.dispose()

    app = FastAPI(
        title="WTrackerBot Mini App API",
        version=resolved_settings.app_version,
        docs_url=None if resolved_settings.app_environment == "production" else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database_engine = resolved_engine
    app.state.database_session_factory = resolved_session_factory
    app.state.telegram_auth_validator = TelegramInitDataValidator(
        resolved_settings.bot_token.get_secret_value(),
        max_age_seconds=resolved_settings.miniapp_auth_max_age_seconds,
        clock_skew_seconds=resolved_settings.miniapp_auth_clock_skew_seconds,
    )
    app.state.open_food_facts_client = OpenFoodFactsClient(
        base_url=str(resolved_settings.open_food_facts_base_url),
        user_agent=resolved_settings.open_food_facts_user_agent,
        timeout_seconds=resolved_settings.open_food_facts_timeout_seconds,
        retries=resolved_settings.open_food_facts_retries,
        concurrency=resolved_settings.open_food_facts_concurrency,
        max_response_bytes=resolved_settings.open_food_facts_max_response_bytes,
        circuit_failures=resolved_settings.open_food_facts_circuit_failures,
        circuit_cooldown_seconds=(
            resolved_settings.open_food_facts_circuit_cooldown_seconds
        ),
    )
    app.state.barcode_rate_limiter = BarcodeRateLimiter(
        resolved_settings.barcode_rate_limit_count,
        resolved_settings.barcode_rate_limit_window_seconds,
    )
    app.state.barcode_confirmation_signer = BarcodeConfirmationSigner(
        resolved_settings.bot_token.get_secret_value(),
        resolved_settings.barcode_confirmation_ttl_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.miniapp_cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=["X-Correlation-ID"],
    )
    app.add_middleware(
        RequestLimitMiddleware,
        max_body_bytes=resolved_settings.miniapp_max_request_body_bytes,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    register_error_handlers(app)
    app.include_router(router)
    return app
