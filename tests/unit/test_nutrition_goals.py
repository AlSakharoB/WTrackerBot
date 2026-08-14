from datetime import date
from decimal import Decimal

import pytest

from app.bot.handlers.diary import day_text
from app.bot.keyboards.diary import build_day_keyboard
from app.bot.keyboards.settings import SETTINGS_NUTRITION_GOALS
from app.db.models.nutrition_goal import NutritionGoal
from app.exceptions import ValidationError
from app.services.diary import DaySummary
from app.services.nutrition import MacroPercentages, NutritionValues
from app.services.nutrition_goals import (
    NutritionGoalData,
    calculate_target_progress,
    parse_nutrition_target,
    validate_nutrition_goal,
)


@pytest.mark.parametrize(
    ("consumed", "expected_percentage", "expected_excess"),
    [
        ("0", "0", "0"),
        ("1100", "50", "0"),
        ("2200", "100", "0"),
        ("2376", "108", "176"),
    ],
)
def test_nutrition_target_progress(
    consumed: str,
    expected_percentage: str,
    expected_excess: str,
) -> None:
    progress = calculate_target_progress(Decimal(consumed), Decimal("2200"))

    assert progress.percentage == Decimal(expected_percentage)
    assert progress.excess == Decimal(expected_excess)


@pytest.mark.parametrize(
    ("field", "valid", "invalid"),
    [
        ("kcal_target", "10000", "10000.01"),
        ("protein_target_g", "1000", "1000.01"),
        ("fat_target_g", "1000", "1000.01"),
        ("carbs_target_g", "2000", "2000.01"),
    ],
)
def test_nutrition_target_validation_limits(
    field: str,
    valid: str,
    invalid: str,
) -> None:
    assert parse_nutrition_target(field, valid) == Decimal(valid)
    with pytest.raises(ValidationError):
        parse_nutrition_target(field, invalid)
    with pytest.raises(ValidationError):
        parse_nutrition_target(field, "0")


def test_partial_goal_is_valid_but_empty_goal_is_not() -> None:
    validate_nutrition_goal(
        NutritionGoalData(
            kcal_target=Decimal("2200"),
            protein_target_g=Decimal("160"),
            fat_target_g=None,
            carbs_target_g=None,
        )
    )

    with pytest.raises(ValidationError, match="хотя бы одну"):
        validate_nutrition_goal(NutritionGoalData(None, None, None, None))


def test_day_text_shows_only_configured_targets_and_excess() -> None:
    goal = NutritionGoal(
        id=1,
        user_id=10,
        kcal_target=Decimal("2200"),
        protein_target_g=Decimal("160"),
        fat_target_g=None,
        carbs_target_g=None,
        effective_from=date(2026, 8, 1),
    )
    summary = DaySummary(
        entry_date=date(2026, 8, 14),
        entries=[],
        totals=NutritionValues(
            kcal=Decimal("2370"),
            protein=Decimal("80"),
            fat=Decimal("61"),
            carbs=Decimal("184"),
        ),
        macro_percentages=MacroPercentages(
            protein=Decimal("20"),
            fat=Decimal("35"),
            carbs=Decimal("45"),
        ),
        nutrition_goal=goal,
    )

    text = day_text(summary)

    assert "2370 / 2200 ккал" in text
    assert "██████████ 108%" in text
    assert "+170 ккал" in text
    assert "80 / 160 г" in text
    assert "█████░░░░░ 50%" in text
    assert "🥑 Жиры\n" not in text
    assert "🍞 Углеводы\n" not in text


def test_day_keyboard_links_to_nutrition_goal_settings() -> None:
    keyboard = build_day_keyboard()
    callbacks = [
        button.callback_data for row in keyboard.inline_keyboard for button in row
    ]

    assert SETTINGS_NUTRITION_GOALS in callbacks
