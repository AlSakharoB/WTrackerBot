from datetime import UTC, date, datetime
from decimal import Decimal

from app.user_settings import NumberFormat
from app.utils.decimal import reset_number_format, set_number_format
from app.utils.formatting import (
    format_date,
    format_date_long,
    format_datetime,
    format_signed_decimal,
)


def test_date_and_datetime_formatting_is_consistent() -> None:
    value = date(2026, 8, 11)
    measured_at = datetime(2026, 8, 10, 21, 30, tzinfo=UTC)

    assert format_date(value) == "11.08.2026"
    assert format_date_long(value) == "11 августа 2026"
    assert format_datetime(measured_at, "Europe/Moscow") == "11.08.2026 00:30"


def test_signed_decimal_adds_plus_only_for_positive_values() -> None:
    assert format_signed_decimal(Decimal("1.50")) == "+1.5"
    assert format_signed_decimal(Decimal("-1.50")) == "-1.5"
    assert format_signed_decimal(Decimal("0")) == "0"


def test_user_number_format_controls_decimal_precision() -> None:
    one_decimal = set_number_format(NumberFormat.ONE_DECIMAL)
    try:
        assert format_signed_decimal(Decimal("3.64")) == "+3.6"
        assert format_signed_decimal(Decimal("31")) == "+31.0"
    finally:
        reset_number_format(one_decimal)

    two_decimals = set_number_format(NumberFormat.TWO_DECIMALS)
    try:
        assert format_signed_decimal(Decimal("3.6")) == "+3.60"
        assert format_signed_decimal(Decimal("31")) == "+31.00"
    finally:
        reset_number_format(two_decimals)
