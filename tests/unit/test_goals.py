from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.bot.handlers.goals import goal_card
from app.bot.keyboards.goals import (
    GoalActionCallback,
    build_achieved_goal_keyboard,
    build_goal_without_progress_keyboard,
)
from app.db.models.goal import WeightGoal
from app.db.models.weight import WeightEntry
from app.exceptions import ValidationError
from app.services.goals import (
    GoalDetails,
    GoalProgress,
    calculate_goal_progress,
    parse_target_date,
)
from app.utils.progress import build_progress_bar


@pytest.mark.parametrize(
    ("start", "target", "current", "expected"),
    [
        (
            "90",
            "80",
            "85",
            GoalProgress(Decimal("50"), Decimal("5"), Decimal("5"), False),
        ),
        (
            "70",
            "80",
            "75",
            GoalProgress(Decimal("50"), Decimal("5"), Decimal("5"), False),
        ),
        (
            "90",
            "80",
            "80",
            GoalProgress(Decimal("100"), Decimal("10"), Decimal("0"), True),
        ),
        (
            "90",
            "80",
            "75",
            GoalProgress(Decimal("100"), Decimal("10"), Decimal("0"), True),
        ),
        (
            "70",
            "80",
            "85",
            GoalProgress(Decimal("100"), Decimal("10"), Decimal("0"), True),
        ),
        (
            "90",
            "80",
            "95",
            GoalProgress(Decimal("0"), Decimal("0"), Decimal("15"), False),
        ),
        (
            "80",
            "80",
            "80",
            GoalProgress(Decimal("100"), Decimal("0"), Decimal("0"), True),
        ),
    ],
)
def test_calculate_goal_progress(
    start: str,
    target: str,
    current: str,
    expected: GoalProgress,
) -> None:
    result = calculate_goal_progress(
        start_weight_kg=Decimal(start),
        target_weight_kg=Decimal(target),
        current_weight_kg=Decimal(current),
    )

    assert result == expected


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [
        ("0", "░░░░░░░░░░"),
        ("1", "░░░░░░░░░░"),
        ("49", "████░░░░░░"),
        ("50", "█████░░░░░"),
        ("99", "█████████░"),
        ("100", "██████████"),
        ("-12", "░░░░░░░░░░"),
        ("127", "██████████"),
    ],
)
def test_build_progress_bar_clamps_and_fills_segments(
    percentage: str,
    expected: str,
) -> None:
    assert build_progress_bar(Decimal(percentage)) == expected


def test_build_progress_bar_supports_custom_length() -> None:
    assert build_progress_bar(Decimal("50"), length=4) == "██░░"
    with pytest.raises(ValueError):
        build_progress_bar(Decimal("50"), length=0)


def goal_details(
    *,
    start: str | None,
    target: str,
    current: str | None,
    target_date: date | None = None,
) -> GoalDetails:
    goal = WeightGoal(
        id=1,
        user_id=10,
        target_weight_kg=Decimal(target),
        target_date=target_date,
        start_weight_kg=Decimal(start) if start is not None else None,
    )
    current_entry = (
        WeightEntry(
            id=2,
            user_id=10,
            weight_kg=Decimal(current),
            measured_at=datetime(2026, 8, 14, 8, tzinfo=UTC),
        )
        if current is not None
        else None
    )
    progress = (
        calculate_goal_progress(
            start_weight_kg=Decimal(start),
            target_weight_kg=Decimal(target),
            current_weight_kg=Decimal(current),
        )
        if start is not None and current is not None
        else None
    )
    return GoalDetails(goal=goal, current_weight=current_entry, progress=progress)


def test_goal_card_shows_weight_loss_progress() -> None:
    card = goal_card(
        goal_details(
            start="90",
            target="75",
            current="82.5",
            target_date=date(2026, 12, 15),
        )
    )

    assert "🎯 <b>Цель по весу</b>" in card
    assert "Старт: 90 кг" in card
    assert "Сейчас: 82.5 кг" in card
    assert "Цель: 75 кг" in card
    assert "Прогресс: 50%" in card
    assert "█████░░░░░ 50%" in card
    assert "Сброшено: 7.5 кг" in card
    assert "Осталось: 7.5 кг" in card
    assert "Срок: 15.12.2026" in card


def test_goal_card_shows_weight_gain_and_no_deadline() -> None:
    card = goal_card(goal_details(start="65", target="75", current="70"))

    assert "Прогресс: 50%" in card
    assert "Набрано: 5 кг" in card
    assert "Осталось: 5 кг" in card
    assert "Срок: не указан" in card


def test_goal_card_marks_achieved_goal_without_completing_it() -> None:
    card = goal_card(goal_details(start="90", target="80", current="78"))

    assert "🎯 <b>Цель достигнута!</b>" in card
    assert "██████████ 100%" in card
    assert "Осталось: 0 кг" in card


@pytest.mark.parametrize(
    ("start", "target", "current", "expected"),
    [
        ("90", "80", "85", "█████░░░░░ 50%"),
        ("60", "70", "65", "█████░░░░░ 50%"),
        ("90", "80", "80", "██████████ 100%"),
    ],
)
def test_d7_progress_bar_scenarios(
    start: str,
    target: str,
    current: str,
    expected: str,
) -> None:
    assert expected in goal_card(
        goal_details(start=start, target=target, current=current)
    )


def test_goal_card_without_start_does_not_show_fake_progress() -> None:
    card = goal_card(goal_details(start=None, target="75", current=None))

    assert card.startswith("🎯 <b>Цель: 75 кг</b>")
    assert "Чтобы считать прогресс" in card
    assert "Срок: не указан" in card
    assert "Прогресс:" not in card
    assert "0%" not in card


def test_special_goal_keyboards_offer_required_actions() -> None:
    achieved = build_achieved_goal_keyboard(1)
    without_progress = build_goal_without_progress_keyboard(1)

    assert [row[0].text for row in achieved.inline_keyboard[:2]] == [
        "✅ Завершить цель",
        "🎯 Поставить новую цель",
    ]
    assert without_progress.inline_keyboard[0][0].text == "➕ Добавить вес"
    assert without_progress.inline_keyboard[0][0].callback_data == "weight:add"


def test_parse_target_date_accepts_supported_formats() -> None:
    assert parse_target_date("15.12.2026").isoformat() == "2026-12-15"
    assert parse_target_date("2027-01-20").isoformat() == "2027-01-20"


def test_parse_target_date_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        parse_target_date("31.02.2027")


def test_goal_callback_fits_telegram_limit() -> None:
    callback_data = GoalActionCallback(
        action="complete_confirm",
        goal_id=9_223_372_036_854_775_807,
    ).pack()

    assert len(callback_data.encode()) <= 64
