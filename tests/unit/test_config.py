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
    ],
)
def test_settings_reject_invalid_values(
    override: dict[str, str],
    expected_message: str,
) -> None:
    values = VALID_SETTINGS | override

    with pytest.raises(ValidationError, match=expected_message):
        Settings(**values, _env_file=None)
