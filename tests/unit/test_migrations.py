import hashlib
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.config import Settings
from scripts import migrate


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


def test_compose_orders_db_migrate_bot_and_persists_backups() -> None:
    project_root = Path(__file__).parents[2]
    compose = project_root.joinpath("docker-compose.yml").read_text()
    backup_dockerfile = project_root.joinpath("docker/backup.Dockerfile").read_text()
    deploy = project_root.joinpath("scripts/deploy.sh").read_text()

    assert "migrate:" in compose
    assert "backup:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "postgres_backups:/backups" in compose
    assert 'command: ["python", "-m", "scripts.migrate"]' in compose
    assert "postgres:16-alpine" in backup_dockerfile
    assert "docker compose" in deploy
    assert "scripts/healthcheck.py" in deploy
