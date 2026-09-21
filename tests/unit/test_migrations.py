import hashlib
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.config import Settings
from scripts import migrate

PROJECT_ROOT = Path(__file__).parents[2]


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "bot_token": "test-token",
        "database_url": (
            "postgresql+asyncpg://db-user:secret-password@db:5432/nutrition_bot"
        ),
        "app_environment": "production",
        "migration_backup_dir": tmp_path,
        "migration_backup_marker": tmp_path / ".last-verified",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_verified_backup_uses_pg_dump_and_pg_restore(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        calls.append((command, environment))
        if command[0] == "pg_dump":
            output = next(
                item.removeprefix("--file=")
                for item in command
                if item.startswith("--file=")
            )
            Path(output).write_bytes(b"valid custom dump")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(migrate.subprocess, "run", fake_run)

    backup = migrate.create_verified_backup(make_settings(tmp_path))

    assert backup.is_file()
    assert [call[0][0] for call in calls] == ["pg_dump", "pg_restore"]
    assert calls[0][1]["PGPASSWORD"] == "secret-password"
    assert "secret-password" not in " ".join(calls[0][0])


def test_backup_failure_blocks_alembic(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(migrate, "check_database_health", AsyncMock())
    monkeypatch.setattr(
        migrate,
        "verify_precreated_backup",
        Mock(side_effect=migrate.MigrationFlowError("backup failed")),
    )
    alembic = Mock()
    monkeypatch.setattr(migrate, "run_alembic_upgrade", alembic)

    with pytest.raises(migrate.MigrationFlowError, match="backup failed"):
        migrate.run_migration_flow(make_settings(tmp_path))

    alembic.assert_not_called()


def test_failed_alembic_blocks_revision_verification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(migrate, "check_database_health", AsyncMock())
    monkeypatch.setattr(
        migrate,
        "verify_precreated_backup",
        Mock(return_value=tmp_path / "backup.dump"),
    )
    monkeypatch.setattr(
        migrate,
        "run_alembic_upgrade",
        Mock(side_effect=migrate.MigrationFlowError("alembic failed")),
    )
    verify = AsyncMock()
    monkeypatch.setattr(migrate, "verify_database_revision", verify)

    with pytest.raises(migrate.MigrationFlowError, match="alembic failed"):
        migrate.run_migration_flow(make_settings(tmp_path))

    verify.assert_not_awaited()


def test_development_override_is_explicit_and_production_rejects_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with pytest.raises(ValidationError, match="verified backup"):
        make_settings(tmp_path, allow_migration_without_backup=True)

    settings = make_settings(
        tmp_path,
        app_environment="development",
        allow_migration_without_backup=True,
    )
    monkeypatch.setattr(migrate, "check_database_health", AsyncMock())
    monkeypatch.setattr(
        migrate,
        "create_verified_backup",
        Mock(side_effect=OSError("disk unavailable")),
    )
    alembic = Mock()
    monkeypatch.setattr(migrate, "run_alembic_upgrade", alembic)
    monkeypatch.setattr(migrate, "verify_database_revision", AsyncMock())

    assert migrate.run_migration_flow(settings) is None
    alembic.assert_called_once_with()


def test_precreated_backup_marker_verifies_checksum(tmp_path: Path) -> None:
    backup = tmp_path / "database.dump"
    backup.write_bytes(b"postgres-16-custom-dump")
    checksum = hashlib.sha256(backup.read_bytes()).hexdigest()
    tmp_path.joinpath(".last-verified").write_text(f"{backup.name} {checksum}\n")

    assert migrate.verify_precreated_backup(make_settings(tmp_path)) == backup

    backup.write_bytes(b"tampered")
    with pytest.raises(migrate.MigrationFlowError, match="checksum mismatch"):
        migrate.verify_precreated_backup(make_settings(tmp_path))


def test_compose_orders_db_migrate_long_running_services_and_persists_backups() -> None:
    compose = PROJECT_ROOT.joinpath("docker-compose.yml").read_text()
    backup_dockerfile = PROJECT_ROOT.joinpath("docker/backup.Dockerfile").read_text()
    backup_script = PROJECT_ROOT.joinpath("docker/backup.sh").read_text()
    deploy = PROJECT_ROOT.joinpath("scripts/deploy.sh").read_text()

    assert "migrate:" in compose
    assert "backup:" in compose
    assert "web:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "postgres_backups:/backups" in compose
    assert 'command: ["python", "-m", "scripts.migrate"]' in compose
    assert 'command: ["python", "-m", "app.web.main"]' in compose
    assert 'test: ["CMD", "python", "scripts/web_healthcheck.py"]' in compose
    assert "MINIAPP_HOST: 0.0.0.0" in compose
    assert '"${MINIAPP_PORT:-8080}"' in compose
    assert "8080:8080" not in compose
    assert "postgres:16-alpine" in backup_dockerfile
    assert "awk 'NR > 2'" in backup_script
    assert 'rm -f "$expired_backup"' in backup_script
    assert "docker compose" in deploy
    assert "scripts/healthcheck.py" in deploy
    assert "docker image prune -a -f" in deploy
    assert "docker builder prune -a -f" in deploy
    assert "rm -f backup migrate" in deploy
    assert '"$script_dir/sync_env.sh"' in deploy
    assert deploy.index('"$script_dir/sync_env.sh"') < deploy.index(
        "compose build backup bot miniapp"
    )
    assert deploy.index("scripts/healthcheck.py") < deploy.index(
        "docker image prune -a -f"
    )
    assert "--volumes" not in deploy


def test_backup_script_keeps_only_two_latest_verified_dumps(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for index, name in enumerate(("old-a.dump", "old-b.dump", "old-c.dump")):
        path = backup_dir / name
        path.write_bytes(name.encode())
        os.utime(path, (100 + index, 100 + index))

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cli = PROJECT_ROOT / "tests/fixtures/fake_backup_cli.sh"
    for command in ("pg_dump", "pg_restore", "date"):
        bin_dir.joinpath(command).symlink_to(fake_cli)

    marker = backup_dir / ".last-verified"
    environment = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "MIGRATION_BACKUP_DIR": str(backup_dir),
        "MIGRATION_BACKUP_MARKER": str(marker),
        "PGDATABASE": "nutrition_bot",
    }
    result = subprocess.run(
        [str(PROJECT_ROOT / "docker/backup.sh")],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    dumps = sorted(path.name for path in backup_dir.glob("*.dump"))
    assert dumps == ["nutrition_bot_20260920T120000Z.dump", "old-c.dump"]
    marker_name, marker_checksum = marker.read_text(encoding="utf-8").split()
    newest = backup_dir / marker_name
    assert newest.name == "nutrition_bot_20260920T120000Z.dump"
    assert marker_checksum == hashlib.sha256(newest.read_bytes()).hexdigest()
