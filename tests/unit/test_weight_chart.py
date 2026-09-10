import struct
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import matplotlib.pyplot as plt
import pytest

from app.exceptions import ValidationError
from app.services.weight_chart import (
    CHART_PERIODS,
    WeightChartData,
    WeightChartPoint,
    custom_chart_range,
    fixed_chart_range,
    parse_chart_date,
)
from app.utils.charts import render_weight_chart


def make_chart_data(point_count: int) -> WeightChartData:
    period = custom_chart_range(date(2026, 8, 1), date(2026, 8, 14))
    points = tuple(
        WeightChartPoint(
            measured_at=datetime(2026, 8, 1, 8, tzinfo=UTC) + timedelta(days=index),
            weight_kg=Decimal("84") - Decimal(index) / 10,
        )
        for index in range(point_count)
    )
    return WeightChartData(
        period=period,
        points=points,
        target_weight_kg=Decimal("80") if point_count > 1 else None,
    )


def png_dimensions(content: bytes) -> tuple[int, int]:
    assert content.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", content[16:24])


@pytest.mark.parametrize("days", CHART_PERIODS)
def test_fixed_chart_periods_are_inclusive_and_end_today(days: int) -> None:
    today = date(2026, 8, 14)
    period = fixed_chart_range(days, today)

    assert period.date_to == today
    assert period.days == days


def test_custom_chart_range_accepts_365_and_rejects_366_days() -> None:
    accepted = custom_chart_range(date(2025, 1, 1), date(2025, 12, 31))
    assert accepted.days == 365

    with pytest.raises(ValidationError, match="365"):
        custom_chart_range(date(2024, 1, 1), date(2024, 12, 31))


def test_custom_chart_range_accepts_364_days() -> None:
    accepted = custom_chart_range(date(2025, 1, 2), date(2025, 12, 31))

    assert accepted.days == 364


def test_custom_chart_range_rejects_reversed_dates() -> None:
    with pytest.raises(ValidationError, match="раньше"):
        custom_chart_range(date(2026, 8, 2), date(2026, 8, 1))


def test_seven_day_average_uses_trailing_calendar_window() -> None:
    data = make_chart_data(8)

    averages = data.moving_average_7d

    assert averages[:6] == (None,) * 6
    assert averages[6] == Decimal("83.7")
    assert averages[7] == Decimal("83.6")


def test_parse_chart_date_accepts_supported_formats() -> None:
    assert parse_chart_date("14.08.2026") == date(2026, 8, 14)
    assert parse_chart_date("2026-08-14") == date(2026, 8, 14)

    with pytest.raises(ValidationError):
        parse_chart_date("31.02.2026")


def test_render_weight_chart_rejects_empty_data() -> None:
    with pytest.raises(ValueError, match="at least one point"):
        render_weight_chart(make_chart_data(0))


@pytest.mark.parametrize("point_count", [1, 14])
def test_render_weight_chart_returns_1200_by_675_png_and_closes_figure(
    point_count: int,
) -> None:
    figure_count = len(plt.get_fignums())

    image = render_weight_chart(make_chart_data(point_count))
    content = image.getvalue()

    assert png_dimensions(content) == (1200, 675)
    assert image.tell() == 0
    assert len(content) > 10_000
    assert len(plt.get_fignums()) == figure_count
    image.close()
