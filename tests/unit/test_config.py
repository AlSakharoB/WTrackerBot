import pytest
from pydantic import ValidationError

from app.config import Settings

VALID_SETTINGS = {
    "bot_token": "123456:abcdefghijklmnopqrstuvwxyzABCDE1234567890",
    "database_url": "postgresql+asyncpg://postgres:postgres@db/nutrition_bot",
}


def test_settings_accept_valid_environment() -> None:
    settings = Settings(**VALID_SETTINGS, _env_file=None)

    assert settings.bot_token.get_secret_value() == VALID_SETTINGS["bot_token"]
    assert settings.log_level == "INFO"
    assert settings.default_timezone == "Europe/Moscow"
    assert settings.app_environment == "development"
    assert settings.health_heartbeat_interval_seconds == 30
    assert settings.reminder_misfire_grace_seconds == 1800
    assert settings.app_version == "0.1.0"
    assert settings.git_commit_sha == "unknown"
    assert str(settings.migration_backup_dir) == "/backups"
    assert str(settings.migration_backup_marker) == "/backups/.last-verified"
    assert not settings.allow_migration_without_backup
    assert settings.shutdown_drain_timeout_seconds == 20
    assert settings.rate_limit_messages_count == 10
    assert settings.rate_limit_messages_window_seconds == 10
    assert settings.rate_limit_callbacks_count == 20
    assert settings.rate_limit_callbacks_window_seconds == 10
    assert settings.rate_limit_search_count == 5
    assert settings.rate_limit_search_window_seconds == 10
    assert settings.rate_limit_weight_chart_count == 3
    assert settings.rate_limit_weight_chart_window_seconds == 60
    assert settings.rate_limit_share_create_count == 10
    assert settings.rate_limit_share_create_window_seconds == 60
    assert settings.rate_limit_share_open_count == 20
    assert settings.rate_limit_share_open_window_seconds == 60
    assert settings.rate_limit_share_import_count == 10
    assert settings.rate_limit_share_import_window_seconds == 60
    assert settings.rate_limit_share_rotate_count == 5
    assert settings.rate_limit_share_rotate_window_seconds == 60
    assert settings.rate_limit_notice_cooldown_seconds == 5
    assert settings.action_lock_ttl_seconds == 20
    assert settings.share_link_ttl_days == 30
    assert settings.share_package_retention_days == 30
    assert settings.share_max_items == 20
    assert settings.share_max_ingredients == 100
    assert settings.share_max_components == 200
    assert settings.share_max_payload_bytes == 262_144
    assert settings.miniapp_enabled is False
    assert str(settings.miniapp_public_url) == "http://localhost:5173/"
    assert settings.miniapp_host == "127.0.0.1"
    assert settings.miniapp_port == 8080
    assert settings.miniapp_auth_max_age_seconds == 300
    assert settings.miniapp_auth_clock_skew_seconds == 30
    assert settings.miniapp_max_auth_header_bytes == 8192
    assert settings.miniapp_max_request_body_bytes == 65_536
    assert settings.miniapp_cors_origins == ("http://localhost:5173",)
    assert settings.web_mutation_receipt_ttl_hours == 24
    assert settings.web_mutation_receipt_cleanup_seconds == 3600
    assert str(settings.open_food_facts_base_url) == "https://world.openfoodfacts.org/"
    assert settings.open_food_facts_timeout_seconds == 6
    assert settings.open_food_facts_retries == 1
    assert settings.open_food_facts_concurrency == 4
    assert settings.open_food_facts_max_response_bytes == 524_288
    assert settings.open_food_facts_positive_cache_seconds == 86_400
    assert settings.open_food_facts_negative_cache_seconds == 1800
    assert settings.barcode_rate_limit_count == 10
    assert settings.barcode_rate_limit_window_seconds == 60
    assert settings.barcode_confirmation_ttl_seconds == 900


def test_settings_normalize_log_level() -> None:
    settings = Settings(**VALID_SETTINGS, log_level="debug", _env_file=None)

    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("override", "expected_message"),
    [
        ({"database_url": "postgresql://db"}, r"postgresql\+asyncpg"),
        ({"log_level": "verbose"}, "Unsupported LOG_LEVEL"),
        ({"default_timezone": "Mars/Olympus"}, "Unknown DEFAULT_TIMEZONE"),
        ({"share_link_ttl_days": "91"}, "less than or equal to 90"),
        ({"share_package_retention_days": "0"}, "greater than or equal to 1"),
        ({"miniapp_auth_max_age_seconds": "29"}, "greater than or equal to 30"),
    ],
)
def test_settings_reject_invalid_values(
    override: dict[str, str],
    expected_message: str,
) -> None:
    values = VALID_SETTINGS | override

    with pytest.raises(ValidationError, match=expected_message):
        Settings(**values, _env_file=None)


def test_settings_parse_miniapp_cors_origins() -> None:
    settings = Settings(
        **VALID_SETTINGS,
        miniapp_cors_origins="https://app.example.com/, http://localhost:5173",
        _env_file=None,
    )

    assert settings.miniapp_cors_origins == (
        "https://app.example.com",
        "http://localhost:5173",
    )


def test_settings_require_https_for_enabled_production_miniapp() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            **VALID_SETTINGS,
            app_environment="production",
            miniapp_enabled=True,
            miniapp_public_url="http://app.example.com",
            _env_file=None,
        )
