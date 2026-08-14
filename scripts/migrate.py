import asyncio
import hashlib
import hmac
import logging
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import Settings, get_settings
from app.core.health import (
    DatabaseRevisionStatus,
    get_database_revision_state,
)
from app.core.logging import setup_logging
from app.db.session import check_database_connection, create_database_engine
from scripts.notify_startup_error import (
    MIGRATION_ALERT_MARKER,
    notify_migration_failure,
)

logger = logging.getLogger(__name__)


class MigrationFlowError(RuntimeError):
    pass


async def check_database_health(database_url: str) -> None:
    engine = create_database_engine(database_url)
    try:
        await check_database_connection(engine)
    finally:
        await engine.dispose()


def create_verified_backup(settings: Settings) -> Path:
    backup_dir = settings.migration_backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    url = make_url(settings.database_url)
    database_name = re.sub(r"[^A-Za-z0-9_.-]", "_", url.database or "database")
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"{database_name}_{timestamp}.dump"
    temporary_path = backup_path.with_suffix(".dump.tmp")
    temporary_path.unlink(missing_ok=True)
    pg_environment = _postgres_environment(settings.database_url)

    dump = subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-password",
            f"--file={temporary_path}",
        ],
        env=pg_environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if dump.returncode != 0 or not temporary_path.is_file():
        temporary_path.unlink(missing_ok=True)
        raise MigrationFlowError("pg_dump failed")
    if temporary_path.stat().st_size == 0:
        temporary_path.unlink(missing_ok=True)
        raise MigrationFlowError("pg_dump created an empty backup")

    verification = subprocess.run(
        ["pg_restore", "--list", str(temporary_path)],
        env=pg_environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if verification.returncode != 0:
        temporary_path.unlink(missing_ok=True)
        raise MigrationFlowError("pg_restore could not verify the backup")
    temporary_path.replace(backup_path)
    return backup_path


def verify_precreated_backup(settings: Settings) -> Path:
    backup_dir = settings.migration_backup_dir.resolve()
    marker = settings.migration_backup_marker.resolve()
    if marker.parent != backup_dir:
        raise MigrationFlowError("backup marker must be inside the backup directory")
    try:
        filename, expected_checksum = marker.read_text().strip().split()
    except (OSError, ValueError) as error:
        raise MigrationFlowError(
            "verified backup marker is missing or invalid"
        ) from error
    backup_path = backup_dir.joinpath(filename).resolve()
    if backup_path.parent != backup_dir or not backup_path.is_file():
        raise MigrationFlowError("verified backup file is missing")
    if backup_path.stat().st_size == 0:
        raise MigrationFlowError("verified backup file is empty")
    digest = hashlib.sha256()
    with backup_path.open("rb") as backup_file:
        for chunk in iter(lambda: backup_file.read(1024 * 1024), b""):
            digest.update(chunk)
    if not hmac.compare_digest(digest.hexdigest(), expected_checksum):
        raise MigrationFlowError("verified backup checksum mismatch")
    return backup_path


def _postgres_environment(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    environment = os.environ.copy()
    if url.host:
        environment["PGHOST"] = url.host
    environment["PGPORT"] = str(url.port or 5432)
    if url.username:
        environment["PGUSER"] = url.username
    if url.password:
        environment["PGPASSWORD"] = url.password
    if url.database:
        environment["PGDATABASE"] = url.database
    ssl_mode = url.query.get("sslmode") or url.query.get("ssl")
    if isinstance(ssl_mode, str):
        environment["PGSSLMODE"] = ssl_mode
    return environment


def run_alembic_upgrade() -> None:
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        stdout=None,
        stderr=None,
        check=False,
    )
    if result.returncode != 0:
        raise MigrationFlowError("alembic upgrade failed")


async def verify_database_revision(database_url: str) -> None:
    engine = create_database_engine(database_url)
    try:
        revision = await get_database_revision_state(engine)
    finally:
        await engine.dispose()
    if revision.status is not DatabaseRevisionStatus.UP_TO_DATE:
        raise MigrationFlowError(f"post-migration revision is {revision.status.value}")


def run_migration_flow(settings: Settings) -> Path | None:
    asyncio.run(check_database_health(settings.database_url))
    logger.info(
        "Database is healthy before migration",
        extra={"operation": "database.migration.health"},
    )

    backup_path: Path | None
    try:
        if settings.app_environment == "production":
            backup_path = verify_precreated_backup(settings)
        else:
            backup_path = create_verified_backup(settings)
    except Exception:
        if not (
            settings.app_environment == "development"
            and settings.allow_migration_without_backup
        ):
            raise
        backup_path = None
        logger.warning(
            "Migration backup failed but development override is enabled",
            exc_info=True,
            extra={"operation": "database.migration.backup"},
        )
    else:
        logger.info(
            "Pre-migration backup verified: %s",
            backup_path.name,
            extra={"operation": "database.migration.backup"},
        )

    run_alembic_upgrade()
    asyncio.run(verify_database_revision(settings.database_url))
    logger.info(
        "Database migration completed and revision verified",
        extra={"operation": "database.migration"},
    )
    MIGRATION_ALERT_MARKER.unlink(missing_ok=True)
    return backup_path


def main() -> None:
    settings = get_settings()
    setup_logging(settings)
    try:
        run_migration_flow(settings)
    except Exception as error:
        logger.critical(
            "Safe migration flow failed",
            exc_info=True,
            extra={
                "operation": "database.migration",
                "exception_type": type(error).__name__,
            },
        )
        try:
            asyncio.run(notify_migration_failure())
        except Exception as notification_error:
            logger.error(
                "Failed to notify administrators about migration failure",
                extra={
                    "operation": "admin_notifications.startup",
                    "exception_type": type(notification_error).__name__,
                },
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
