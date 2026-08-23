import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
SYNC_SCRIPT = PROJECT_ROOT / "scripts/sync_env.sh"


def run_sync(tmp_path: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["ENV_BACKUP_LIMIT"] = "2"
    return subprocess.run(
        [str(SYNC_SCRIPT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_sync_adds_only_missing_values_and_is_idempotent(tmp_path: Path) -> None:
    original = """BOT_TOKEN=real-token
ADMIN_TELEGRAM_IDS=123456
POSTGRES_PASSWORD=real-password
"""
    template = """# Existing values must not be overwritten
BOT_TOKEN=replace-me
ADMIN_TELEGRAM_IDS=
POSTGRES_PASSWORD=postgres
SHARE_LINK_TTL_DAYS=30
RATE_LIMIT_SHARE_OPEN_COUNT=20
"""
    tmp_path.joinpath(".env").write_text(original)
    tmp_path.joinpath(".env.example").write_text(template)

    first = run_sync(tmp_path)

    assert first.returncode == 0
    synchronized = tmp_path.joinpath(".env").read_text()
    assert "BOT_TOKEN=real-token" in synchronized
    assert "ADMIN_TELEGRAM_IDS=123456" in synchronized
    assert "POSTGRES_PASSWORD=real-password" in synchronized
    assert "SHARE_LINK_TTL_DAYS=30" in synchronized
    assert "RATE_LIMIT_SHARE_OPEN_COUNT=20" in synchronized
    backups = list(tmp_path.joinpath(".env.backups").glob("env_*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == original

    second = run_sync(tmp_path)

    assert second.returncode == 0
    assert "already synchronized" in second.stdout
    assert tmp_path.joinpath(".env").read_text() == synchronized
    assert len(list(tmp_path.joinpath(".env.backups").glob("env_*.bak"))) == 1


def test_sync_keeps_only_two_latest_backups(tmp_path: Path) -> None:
    tmp_path.joinpath(".env").write_text("BOT_TOKEN=real-token\n")
    example = tmp_path.joinpath(".env.example")

    for index in range(1, 4):
        example.write_text(
            "BOT_TOKEN=replace-me\n"
            + "".join(f"NEW_VARIABLE_{item}={item}\n" for item in range(1, index + 1))
        )
        assert run_sync(tmp_path).returncode == 0

    backups = list(tmp_path.joinpath(".env.backups").glob("env_*.bak"))
    assert len(backups) == 2


def test_sync_creates_missing_env_and_stops_before_deploy(tmp_path: Path) -> None:
    template = "BOT_TOKEN=replace-me\n"
    tmp_path.joinpath(".env.example").write_text(template)

    result = run_sync(tmp_path)

    assert result.returncode == 3
    assert tmp_path.joinpath(".env").read_text() == template
    assert tmp_path.joinpath(".env").stat().st_mode & 0o777 == 0o600
    assert "Fill secrets" in result.stderr
