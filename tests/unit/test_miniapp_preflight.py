import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
PREFLIGHT_SCRIPT = PROJECT_ROOT / "scripts/miniapp_preflight.sh"

VALID_ENV = {
    "BOT_TOKEN": "secret-bot-token",
    "POSTGRES_PASSWORD": "secret-db-password",
    "DATABASE_URL": "postgresql+asyncpg://postgres:secret@db/nutrition_bot",
    "APP_VERSION": "1.0.3",
    "APP_ENVIRONMENT": "production",
    "MINIAPP_ENABLED": "true",
    "MINIAPP_DOMAIN": "app.example.com",
    "MINIAPP_ACME_EMAIL": "admin@example.com",
    "MINIAPP_PUBLIC_URL": "https://app.example.com",
    "MINIAPP_CORS_ORIGINS": "https://app.example.com",
    "MINIAPP_ALLOWED_TELEGRAM_IDS": "123,456",
    "MINIAPP_MANAGE_MENU_BUTTON": "true",
    "MINIAPP_MENU_BUTTON_TEXT": "Открыть дневник",
}


def run_preflight(
    tmp_path: Path,
    *,
    overrides: dict[str, str] | None = None,
    extra_lines: str = "",
) -> subprocess.CompletedProcess[str]:
    values = VALID_ENV | (overrides or {})
    env_file = tmp_path / ".env"
    env_file.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()) + extra_lines,
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "ENV_FILE": str(env_file),
            "COMPOSE_FILE": str(compose_file),
            "MINIAPP_PREFLIGHT_SKIP_SYSTEM_CHECKS": "true",
        }
    )
    return subprocess.run(
        [str(PREFLIGHT_SCRIPT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_preflight_accepts_valid_production_contract_without_leaking_secrets(
    tmp_path: Path,
) -> None:
    result = run_preflight(tmp_path)

    assert result.returncode == 0
    assert "Mini App preflight passed" in result.stdout
    assert VALID_ENV["BOT_TOKEN"] not in result.stdout + result.stderr
    assert VALID_ENV["POSTGRES_PASSWORD"] not in result.stdout + result.stderr


def test_preflight_allows_local_placeholders_while_feature_is_disabled(
    tmp_path: Path,
) -> None:
    result = run_preflight(
        tmp_path,
        overrides={
            "MINIAPP_ENABLED": "false",
            "MINIAPP_DOMAIN": "app.example.com",
            "MINIAPP_PUBLIC_URL": "http://localhost:5173",
            "MINIAPP_CORS_ORIGINS": "http://localhost:5173",
            "MINIAPP_ALLOWED_TELEGRAM_IDS": "",
            "MINIAPP_ACME_EMAIL": "",
        },
    )

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("overrides", "expected_message"),
    [
        (
            {"APP_ENVIRONMENT": "development"},
            "APP_ENVIRONMENT must be production",
        ),
        (
            {"APP_VERSION": "release 1.0.3"},
            "APP_VERSION must be a semantic version",
        ),
        (
            {"MINIAPP_ENABLED": "yes"},
            "MINIAPP_ENABLED must be true or false",
        ),
        (
            {"MINIAPP_DOMAIN": "127.0.0.1"},
            "MINIAPP_DOMAIN must be a public hostname",
        ),
        (
            {"MINIAPP_PUBLIC_URL": "https://app.example.com/profile"},
            "MINIAPP_PUBLIC_URL must exactly match",
        ),
        (
            {"MINIAPP_CORS_ORIGINS": "https://other.example.com"},
            "MINIAPP_CORS_ORIGINS must exactly match",
        ),
        (
            {"MINIAPP_ALLOWED_TELEGRAM_IDS": "123,invalid"},
            "MINIAPP_ALLOWED_TELEGRAM_IDS must contain positive",
        ),
        (
            {"MINIAPP_ACME_EMAIL": "invalid"},
            "MINIAPP_ACME_EMAIL must be a valid email address",
        ),
        (
            {"MINIAPP_MENU_BUTTON_TEXT": "   "},
            "MINIAPP_MENU_BUTTON_TEXT must not be blank",
        ),
    ],
)
def test_preflight_rejects_invalid_contract(
    tmp_path: Path,
    overrides: dict[str, str],
    expected_message: str,
) -> None:
    result = run_preflight(tmp_path, overrides=overrides)

    assert result.returncode == 2
    assert expected_message in result.stderr


def test_preflight_rejects_duplicate_settings(tmp_path: Path) -> None:
    result = run_preflight(
        tmp_path,
        extra_lines="MINIAPP_PUBLIC_URL=https://other.example.com\n",
    )

    assert result.returncode == 2
    assert "MINIAPP_PUBLIC_URL must occur exactly once" in result.stderr
