import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.miniapp_auth_smoke import run_auth_smoke

PROJECT_ROOT = Path(__file__).parents[2]
PRODUCTION_SMOKE = PROJECT_ROOT / "scripts/miniapp_production_smoke.sh"
OBSERVABILITY = PROJECT_ROOT / "scripts/miniapp_observability.sh"
ROLLOUT = PROJECT_ROOT / "scripts/miniapp_rollout.sh"


class FakeResponse:
    def __init__(self, payload: dict[str, str], status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def read(self, amount: int = -1) -> bytes:
        return self._body[:amount]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_authenticated_smoke_keeps_init_data_out_of_output(capsys) -> None:
    secret = "query_id=private&hash=secret"
    open_request = Mock(return_value=FakeResponse({"app_version": "1.0.6"}))

    version = run_auth_smoke(
        "https://app.example.com",
        secret,
        open_request=open_request,
    )

    assert version == "1.0.6"
    request = open_request.call_args.args[0]
    assert request.get_header("Authorization") == f"tma {secret}"
    assert secret not in capsys.readouterr().out


@pytest.mark.parametrize(
    "url",
    (
        "http://app.example.com",
        "https://app.example.com/path",
        "https://app.example.com?debug=1",
        "https://user@app.example.com",
        "invalid",
    ),
)
def test_authenticated_smoke_requires_https_origin(url: str) -> None:
    with pytest.raises(ValueError, match="HTTPS origin"):
        run_auth_smoke(url, "secret", open_request=Mock())


def test_operational_shell_scripts_are_valid_and_do_not_read_secrets() -> None:
    for script in (PRODUCTION_SMOKE, OBSERVABILITY, ROLLOUT):
        result = subprocess.run(
            ["sh", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    production_smoke = PRODUCTION_SMOKE.read_text(encoding="utf-8")
    assert "miniapp_public_audit.sh" in production_smoke
    assert "miniapp_host_audit.sh" in production_smoke
    assert "/weight" in production_smoke
    assert 'name "*.map"' in production_smoke
    assert "release.json" in production_smoke
    assert "BOT_TOKEN" not in production_smoke
    assert "POSTGRES_PASSWORD" not in production_smoke

    observability = OBSERVABILITY.read_text(encoding="utf-8")
    assert "docker stats --no-stream" in observability
    assert "docker system df" in observability
    assert "pg_stat_activity" in observability
    assert "external_product.lookup" in observability
    assert "Authorization" not in observability


def test_rollout_status_reports_counts_without_telegram_ids(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MINIAPP_ENABLED=true\n"
        "MINIAPP_ALLOWED_TELEGRAM_IDS=111222333,444555666\n"
        "MINIAPP_MANAGE_MENU_BUTTON=true\n",
        encoding="utf-8",
    )
    environment = os.environ | {"ENV_FILE": str(env_file)}

    result = subprocess.run(
        [str(ROLLOUT), "require", "limited"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "stage: limited" in result.stdout
    assert "allowlist entries: 2" in result.stdout
    assert "111222333" not in result.stdout
    assert "444555666" not in result.stdout
