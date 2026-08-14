from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def local_today(timezone_name: str, now: datetime | None = None) -> date:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(ZoneInfo(timezone_name)).date()
