from pathlib import Path

import pytest

from scripts import miniapp_security_gate

PROJECT_ROOT = Path(__file__).parents[2]


def test_security_gate_validates_source_contract() -> None:
    checks = miniapp_security_gate.run_security_gate(check_bundle=False)

    assert len(checks) == 7
    assert any("Telegram auth" in check for check in checks)
    assert any("container privileges" in check for check in checks)


def test_security_gate_detects_runtime_secret_in_frontend_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    dist = tmp_path / "frontend/dist"
    dist.mkdir(parents=True)
    tmp_path.joinpath(".env").write_text(
        "BOT_TOKEN=very-secret-runtime-token\n",
        encoding="utf-8",
    )
    dist.joinpath("index.html").write_text(
        "very-secret-runtime-token",
        encoding="utf-8",
    )
    monkeypatch.setattr(miniapp_security_gate, "PROJECT_ROOT", tmp_path)

    with pytest.raises(miniapp_security_gate.SecurityGateError, match="secret-like"):
        miniapp_security_gate.check_frontend_bundle()


def test_release_gate_contains_every_required_automatic_command() -> None:
    release_gate = PROJECT_ROOT.joinpath("scripts/release_gate.sh").read_text(
        encoding="utf-8"
    )

    for command in (
        '"$ruff_bin" check .',
        '"$ruff_bin" format --check .',
        '"$pytest_bin" tests/unit',
        "npm ci",
        "npm run lint",
        "npm run typecheck",
        "npm test -- --run",
        "npm run build",
        "npm run audit:ui",
        "docker compose config --quiet",
        "docker compose build",
        "./scripts/regression.sh",
        "python3 scripts/miniapp_security_gate.py",
    ):
        assert command in release_gate
    assert "RELEASE_GATE_STAGING_ATTESTED" in release_gate
    assert "RELEASE_GATE_CLIENTS_ATTESTED" in release_gate
    assert "RELEASE_GATE_CRITICAL_HIGH_DEFECTS" in release_gate


def test_ui_audit_owns_and_stops_its_loopback_vite_server() -> None:
    package = PROJECT_ROOT.joinpath("frontend/package.json").read_text(encoding="utf-8")
    wrapper = PROJECT_ROOT.joinpath("frontend/scripts/run-ui-audit.mjs").read_text(
        encoding="utf-8"
    )

    assert '"audit:ui": "node scripts/run-ui-audit.mjs"' in package
    assert '"127.0.0.1"' in wrapper
    assert 'server.kill("SIGTERM")' in wrapper
    assert 'server.kill("SIGKILL")' in wrapper
    assert 'await import("./capture-ui-baseline.mjs")' in wrapper


def test_server_runbook_covers_required_operations_without_secrets() -> None:
    runbook = PROJECT_ROOT.joinpath("MINIAPP_SERVER_RUNBOOK.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "DNS",
        "firewall",
        "Первый deploy",
        "Обычный deploy",
        "Health, logs и версии",
        "BotFather",
        "MINIAPP_ENABLED=false",
        "Rollback",
        "Disk и Docker cleanup",
        "Backup и restore",
        "docker compose down -v",
        "miniapp_production_smoke.sh",
    ):
        assert required in runbook
    assert "secret-bot-token" not in runbook
    assert "secret-db-password" not in runbook
