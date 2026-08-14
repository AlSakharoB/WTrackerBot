from __future__ import annotations

import os
from collections import deque
from datetime import datetime, time, timedelta
from io import BytesIO
from threading import Lock

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from app.services.weight_chart import WeightChartData, WeightChartPoint
from app.utils.decimal import format_decimal
from app.utils.formatting import format_signed_decimal

_RENDER_LOCK = Lock()


def render_weight_chart(data: WeightChartData) -> BytesIO:
    if not data.points:
        raise ValueError("Weight chart requires at least one point")

    with _RENDER_LOCK:
        figure = None
        try:
            figure = plt.figure(figsize=(12, 6.75), dpi=100)
            figure.patch.set_facecolor("#FAFBFC")
            axes = figure.add_axes((0.085, 0.14, 0.86, 0.57))
            axes.set_facecolor("#FAFBFC")

            dates = [point.measured_at for point in data.points]
            weights = [float(point.weight_kg) for point in data.points]
            first = data.first
            last = data.last
            change = data.change_kg
            assert first is not None and last is not None and change is not None

            change_color = "#16835D" if change < 0 else "#C2493D"
            if change == 0:
                change_color = "#667085"
            figure.text(
                0.085,
                0.91,
                "Динамика веса",
                fontsize=22,
                fontweight="bold",
                color="#17212B",
                ha="left",
                va="center",
            )
            period_dates = (
                f"{data.period.date_from:%d.%m.%Y} — {data.period.date_to:%d.%m.%Y}"
            )
            period_prefix = (
                "" if data.period.label[:1].isdigit() else f"{data.period.label}  ·  "
            )
            figure.text(
                0.085,
                0.85,
                f"{period_prefix}{period_dates}  ·  Записей: {len(data.points)}",
                fontsize=11,
                color="#667085",
                ha="left",
                va="center",
            )
            figure.text(
                0.945,
                0.91,
                f"{format_decimal(last.weight_kg)} кг",
                fontsize=25,
                fontweight="bold",
                color="#17212B",
                ha="right",
                va="center",
            )
            figure.text(
                0.945,
                0.85,
                f"{format_signed_decimal(change)} кг за период",
                fontsize=12,
                fontweight="normal",
                color=change_color,
                ha="right",
                va="center",
            )

            if len(data.points) == 1:
                axes.scatter(
                    dates,
                    weights,
                    color="#2563EB",
                    edgecolor="#FFFFFF",
                    linewidth=2.5,
                    s=110,
                    label="Измерения",
                    zorder=5,
                )
            else:
                axes.plot(
                    dates,
                    weights,
                    color="#2563EB",
                    linewidth=3,
                    marker="o",
                    markersize=5.5,
                    markerfacecolor="#FFFFFF",
                    markeredgewidth=2,
                    label="Измерения",
                    solid_capstyle="round",
                    solid_joinstyle="round",
                    zorder=4,
                )

            average = _seven_day_average(data.points)
            if average is not None:
                average_dates, average_weights = average
                axes.plot(
                    average_dates,
                    average_weights,
                    color="#E8872D",
                    linewidth=2.2,
                    label="Среднее за 7 дней",
                    solid_capstyle="round",
                    zorder=5,
                )

            visible_values = list(weights)
            show_goal_line = False
            if data.target_weight_kg is not None:
                target = float(data.target_weight_kg)
                data_span = max(max(weights) - min(weights), 1.0)
                show_goal_line = (
                    min(weights) - max(4.0, data_span)
                    <= target
                    <= max(weights) + max(4.0, data_span)
                )
                if show_goal_line:
                    visible_values.append(target)

            value_span = max(max(visible_values) - min(visible_values), 1.0)
            padding = max(value_span * 0.18, 0.45)
            y_min = min(visible_values) - padding
            y_max = max(visible_values) + padding
            axes.set_ylim(y_min, y_max)

            if len(data.points) > 1:
                axes.fill_between(
                    dates,
                    weights,
                    y_min,
                    color="#2563EB",
                    alpha=0.07,
                    linewidth=0,
                    zorder=1,
                )
                axes.scatter(
                    [dates[-1]],
                    [weights[-1]],
                    color="#2563EB",
                    edgecolor="#FFFFFF",
                    linewidth=3,
                    s=125,
                    zorder=7,
                )

            if data.target_weight_kg is not None and show_goal_line:
                target = float(data.target_weight_kg)
                axes.axhline(
                    target,
                    color="#1C9A6C",
                    linewidth=2,
                    linestyle=(0, (5, 5)),
                    label="_nolegend_",
                    zorder=2,
                )
                axes.text(
                    0.995,
                    target,
                    f"  цель {format_decimal(data.target_weight_kg)} кг  ",
                    transform=axes.get_yaxis_transform(),
                    ha="right",
                    va="bottom",
                    fontsize=10,
                    fontweight="normal",
                    color="#13734F",
                    backgroundcolor="#FAFBFC",
                    zorder=6,
                )

            timezone = data.points[0].measured_at.tzinfo
            range_start = datetime.combine(data.period.date_from, time.min, timezone)
            range_end = datetime.combine(data.period.date_to, time.max, timezone)
            axes.set_xlim(range_start, range_end)
            if data.period.days <= 14:
                date_locator = mdates.DayLocator(interval=2, tz=timezone)
            elif data.period.days <= 45:
                date_locator = mdates.DayLocator(interval=5, tz=timezone)
            elif data.period.days <= 100:
                date_locator = mdates.DayLocator(interval=14, tz=timezone)
            elif data.period.days <= 200:
                date_locator = mdates.MonthLocator(interval=1, tz=timezone)
            else:
                date_locator = mdates.MonthLocator(interval=2, tz=timezone)
            axes.xaxis.set_major_locator(date_locator)
            axes.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m", tz=timezone))
            axes.yaxis.set_major_formatter(
                FuncFormatter(lambda value, _: f"{value:g} кг")
            )
            axes.grid(axis="y", color="#E4E8EE", linewidth=1)
            axes.grid(axis="x", visible=False)
            axes.spines[:].set_visible(False)
            axes.tick_params(
                axis="both",
                colors="#667085",
                labelsize=10,
                length=0,
                pad=10,
            )
            handles, labels = axes.get_legend_handles_labels()
            if data.target_weight_kg is not None and not show_goal_line:
                figure.text(
                    0.945,
                    0.79,
                    f"Цель: {format_decimal(data.target_weight_kg)} кг",
                    fontsize=10,
                    color="#13734F",
                    ha="right",
                    va="center",
                )
            axes.legend(
                handles,
                labels,
                loc="lower left",
                bbox_to_anchor=(-0.005, 1.025),
                ncol=3,
                frameon=False,
                fontsize=10,
                handlelength=2.5,
                handletextpad=0.7,
                columnspacing=2,
                labelcolor="#475467",
                borderaxespad=0,
            )
            output = BytesIO()
            figure.savefig(
                output,
                format="png",
                dpi=100,
                facecolor=figure.get_facecolor(),
            )
            output.seek(0)
            return output
        finally:
            if figure is not None:
                plt.close(figure)


def _seven_day_average(
    points: tuple[WeightChartPoint, ...],
) -> tuple[list[datetime], list[float]] | None:
    if len(points) < 7:
        return None
    if points[-1].measured_at - points[0].measured_at < timedelta(days=6):
        return None

    window: deque[WeightChartPoint] = deque()
    averages: list[float] = []
    dates: list[datetime] = []
    total = 0.0
    full_window_at = points[0].measured_at + timedelta(days=6)
    for point in points:
        earliest = point.measured_at - timedelta(days=6)
        while window and window[0].measured_at < earliest:
            total -= float(window.popleft().weight_kg)
        window.append(point)
        total += float(point.weight_kg)
        if point.measured_at >= full_window_at:
            dates.append(point.measured_at)
            averages.append(total / len(window))
    return dates, averages
