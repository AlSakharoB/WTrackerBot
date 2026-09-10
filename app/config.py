from functools import lru_cache
from logging import getLevelNamesMapping
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    bot_token: SecretStr = Field(min_length=1)
    database_url: str = Field(min_length=1)
    log_level: str = "INFO"
    default_timezone: str = "Europe/Moscow"
    app_environment: Literal["development", "production"] = "development"
    app_version: str = Field(default="0.1.0", min_length=1, max_length=64)
    git_commit_sha: str = Field(default="unknown", min_length=1, max_length=64)
    migration_backup_dir: Path = Path("/backups")
    migration_backup_marker: Path = Path("/backups/.last-verified")
    allow_migration_without_backup: bool = False
    health_heartbeat_interval_seconds: int = Field(default=30, ge=1, le=3600)
    reminder_misfire_grace_seconds: int = Field(default=1800, ge=900, le=1800)
    shutdown_drain_timeout_seconds: int = Field(default=20, ge=1, le=25)
    rate_limit_messages_count: int = Field(default=10, ge=1, le=10000)
    rate_limit_messages_window_seconds: int = Field(default=10, ge=1, le=3600)
    rate_limit_callbacks_count: int = Field(default=20, ge=1, le=10000)
    rate_limit_callbacks_window_seconds: int = Field(default=10, ge=1, le=3600)
    rate_limit_search_count: int = Field(default=5, ge=1, le=10000)
    rate_limit_search_window_seconds: int = Field(default=10, ge=1, le=3600)
    rate_limit_weight_chart_count: int = Field(default=3, ge=1, le=10000)
    rate_limit_weight_chart_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
    )
    rate_limit_share_create_count: int = Field(default=10, ge=1, le=10000)
    rate_limit_share_create_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_share_open_count: int = Field(default=20, ge=1, le=10000)
    rate_limit_share_open_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_share_import_count: int = Field(default=10, ge=1, le=10000)
    rate_limit_share_import_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_share_rotate_count: int = Field(default=5, ge=1, le=10000)
    rate_limit_share_rotate_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_notice_cooldown_seconds: int = Field(default=5, ge=0, le=3600)
    action_lock_ttl_seconds: int = Field(default=20, ge=10, le=30)
    admin_telegram_ids: Annotated[set[int], NoDecode] = Field(default_factory=set)
    admin_error_cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    admin_error_max_per_minute: int = Field(default=10, ge=1, le=1000)
    share_link_ttl_days: int = Field(default=30, ge=1, le=90)
    share_package_retention_days: int = Field(default=30, ge=1, le=3650)
    share_max_items: int = Field(default=20, ge=1, le=100)
    share_max_ingredients: int = Field(default=100, ge=1, le=1000)
    share_max_components: int = Field(default=200, ge=1, le=5000)
    share_max_payload_bytes: int = Field(
        default=262_144,
        ge=1024,
        le=1_048_576,
    )
    bot_username: str | None = Field(default=None, min_length=5, max_length=33)
    miniapp_enabled: bool = False
    miniapp_public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:5173")
    miniapp_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    miniapp_port: int = Field(default=8080, ge=1, le=65_535)
    miniapp_auth_max_age_seconds: int = Field(default=300, ge=30, le=3600)
    miniapp_auth_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    miniapp_max_auth_header_bytes: int = Field(default=8192, ge=512, le=65_536)
    miniapp_max_request_body_bytes: int = Field(
        default=65_536,
        ge=1024,
        le=10_485_760,
    )
    miniapp_cors_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:5173",
    )
    web_mutation_receipt_ttl_hours: int = Field(default=24, ge=1, le=168)
    web_mutation_receipt_cleanup_seconds: int = Field(
        default=3600,
        ge=60,
        le=86_400,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            msg = "DATABASE_URL must use the postgresql+asyncpg driver"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in getLevelNamesMapping():
            msg = f"Unsupported LOG_LEVEL: {value}"
            raise ValueError(msg)
        return normalized

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            msg = f"Unknown DEFAULT_TIMEZONE: {value}"
            raise ValueError(msg) from error
        return value

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def parse_admin_telegram_ids(cls, value: object) -> object:
        if value is None or value == "":
            return set()
        if not isinstance(value, str):
            return value

        try:
            parsed = {int(item.strip()) for item in value.split(",") if item.strip()}
        except ValueError as error:
            msg = "ADMIN_TELEGRAM_IDS must be comma-separated integers"
            raise ValueError(msg) from error
        if any(telegram_id <= 0 for telegram_id in parsed):
            msg = "ADMIN_TELEGRAM_IDS must contain positive integers"
            raise ValueError(msg)
        return parsed

    @field_validator("miniapp_cors_origins", mode="before")
    @classmethod
    def parse_miniapp_cors_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        origins = tuple(item.strip().rstrip("/") for item in value.split(","))
        return tuple(origin for origin in origins if origin)

    @field_validator("bot_username", mode="before")
    @classmethod
    def parse_optional_bot_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().removeprefix("@") or None
        return value

    @model_validator(mode="after")
    def reject_production_backup_bypass(self) -> "Settings":
        if self.app_environment == "production" and self.allow_migration_without_backup:
            msg = "Production migrations require a verified backup"
            raise ValueError(msg)
        if self.miniapp_enabled and self.app_environment == "production":
            if self.miniapp_public_url.scheme != "https":
                msg = "Production MINIAPP_PUBLIC_URL must use HTTPS"
                raise ValueError(msg)
            if not self.miniapp_cors_origins:
                msg = "Production Mini App requires at least one CORS origin"
                raise ValueError(msg)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
