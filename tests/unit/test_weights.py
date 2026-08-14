from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.bot.keyboards.weights import WeightEntryCallback
from app.exceptions import ValidationError
from app.services.weights import (
    now_in_timezone,
    parse_measured_at,
    parse_weight,
    today_morning,
    validate_weight,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("20", Decimal("20")),
        ("82.4", Decimal("82.4")),
        ("82,45", Decimal("82.45")),
        ("500.00", Decimal("500.00")),
    ],
)
def test_parse_weight_accepts_valid_values(
    raw_value: str,
    expected: Decimal,
) -> None:
    assert parse_weight(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    ["19.99", "500.01", "82.456", "-80", "NaN", "1e2", "abc"],
)
def test_parse_weight_rejects_invalid_values(raw_value: str) -> None:
    with pytest.raises(ValidationError):
        parse_weight(raw_value)


def test_validate_weight_allows_equivalent_decimal_scale() -> None:
    validate_weight(Decimal("82.400"))

    with pytest.raises(ValidationError):
        validate_weight(Decimal("82.401"))


def test_parse_measured_at_uses_user_timezone() -> None:
    measured_at = parse_measured_at("11.08.2026 08:30", "Europe/Moscow")

    assert measured_at.isoformat() == "2026-08-11T08:30:00+03:00"


def test_weight_quick_times_use_user_timezone() -> None:
    now = datetime(2026, 8, 10, 21, 30, 15, tzinfo=UTC)

    assert now_in_timezone("Europe/Moscow", now).isoformat() == (
        "2026-08-11T00:30:15+03:00"
    )
    assert today_morning("Europe/Moscow", now).isoformat() == (
        "2026-08-11T08:00:00+03:00"
    )


def test_weight_callback_fits_telegram_limit() -> None:
    callback_data = WeightEntryCallback(
        action="delete_confirm",
        entry_id=9_223_372_036_854_775_807,
        page=999_999,
    ).pack()

    assert len(callback_data.encode()) <= 64
