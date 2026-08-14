import asyncio
import sys
from pathlib import Path
from time import time

from app.config import get_settings
from app.core.health import (
    HEARTBEAT_FILE,
    DatabaseRevisionStatus,
    get_database_revision_state,
)
from app.db.session import check_database_connection, create_database_engine


def heartbeat_file_is_fresh(path: Path, *, stale_after_seconds: int) -> bool:
    try:
        age_seconds = max(0, time() - path.stat().st_mtime)
    except OSError:
        return False
    return age_seconds <= stale_after_seconds


async def run_healthcheck() -> int:
    settings = get_settings()
    stale_after_seconds = settings.health_heartbeat_interval_seconds * 3
    if not heartbeat_file_is_fresh(
        HEARTBEAT_FILE,
        stale_after_seconds=stale_after_seconds,
    ):
        print("UNHEALTHY: app heartbeat is missing or stale")
        return 1

    engine = create_database_engine(settings.database_url)
    try:
        await check_database_connection(engine)
        revision = await get_database_revision_state(engine)
    except Exception as error:
        print(f"UNHEALTHY: database check failed ({type(error).__name__})")
        return 1
    finally:
        await engine.dispose()

    if revision.status is not DatabaseRevisionStatus.UP_TO_DATE:
        print(f"UNHEALTHY: database revision is {revision.status.value.upper()}")
        return 1

    print("HEALTHY: app heartbeat, database and revision are OK")
    return 0


def main() -> None:
    try:
        exit_code = asyncio.run(run_healthcheck())
    except Exception as error:
        print(f"UNHEALTHY: healthcheck failed ({type(error).__name__})")
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
