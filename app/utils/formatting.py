from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.utils.decimal import format_decimal

MONTH_NAMES = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_date_long(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month]} {value.year}"


def format_datetime(value: datetime, timezone_name: str) -> str:
    return value.astimezone(ZoneInfo(timezone_name)).strftime("%d.%m.%Y %H:%M")


def format_signed_decimal(
    value: Decimal,
    decimal_places: int | None = None,
) -> str:
    formatted = format_decimal(value, decimal_places)
    return f"+{formatted}" if value > 0 else formatted
