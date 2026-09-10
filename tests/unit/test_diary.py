from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.bot.handlers.diary import finish_food_add
from app.bot.keyboards.diary import (
    DiaryEntryCallback,
    build_entry_list_keyboard,
)
from app.db.models.diary import DiaryEntry
from app.db.models.user import User
from app.exceptions import ValidationError
from app.services.diary import (
    DIARY_ENTRIES_PAGE_SIZE,
    DiaryEntryPage,
    DiaryService,
    parse_entry_date,
    parse_entry_grams,
)
from app.services.nutrition import (
    MacroPercentages,
    NutritionService,
    NutritionValues,
)
from app.user_settings import AfterFoodAddAction
from app.utils.datetime import local_today


def test_daily_nutrition_totals_and_macro_percentages() -> None:
    totals = NutritionService.sum_nutrition(
        [
            NutritionValues(
                kcal=Decimal("330"),
                protein=Decimal("62"),
                fat=Decimal("7.2"),
                carbs=Decimal("0"),
            ),
            NutritionValues(
                kcal=Decimal("270"),
                protein=Decimal("8"),
                fat=Decimal("3"),
                carbs=Decimal("52"),
            ),
        ]
    )

    assert totals == NutritionValues(
        kcal=Decimal("600"),
        protein=Decimal("70"),
        fat=Decimal("10.2"),
        carbs=Decimal("52"),
    )
    percentages = NutritionService.calculate_macro_percentages(
        protein=totals.protein,
        fat=totals.fat,
        carbs=totals.carbs,
    )
    macro_energy = Decimal("70") * 4 + Decimal("10.2") * 9 + Decimal("52") * 4
    assert percentages == MacroPercentages(
        protein=Decimal("280") / macro_energy * 100,
        fat=Decimal("91.8") / macro_energy * 100,
        carbs=Decimal("208") / macro_energy * 100,
    )


def test_macro_percentages_are_zero_without_macros() -> None:
    assert NutritionService.calculate_macro_percentages(
        protein=Decimal("0"),
        fat=Decimal("0"),
        carbs=Decimal("0"),
    ) == MacroPercentages(
        protein=Decimal("0"),
        fat=Decimal("0"),
        carbs=Decimal("0"),
    )


def test_visible_macro_percentages_use_largest_remainder() -> None:
    raw = NutritionService.calculate_macro_percentages(
        protein=Decimal("1"),
        fat=Decimal("1"),
        carbs=Decimal("1"),
    )

    rounded = NutritionService.round_macro_percentages(raw)

    assert rounded == MacroPercentages(
        protein=Decimal("24"),
        fat=Decimal("53"),
        carbs=Decimal("23"),
    )
    assert rounded.protein + rounded.fat + rounded.carbs == 100


def test_visible_macro_percentages_stay_zero_without_macros() -> None:
    rounded = NutritionService.round_macro_percentages(
        MacroPercentages(
            protein=Decimal("0"),
            fat=Decimal("0"),
            carbs=Decimal("0"),
        )
    )

    assert rounded == MacroPercentages(
        protein=Decimal("0"),
        fat=Decimal("0"),
        carbs=Decimal("0"),
    )


def test_entry_parsers_accept_supported_formats() -> None:
    assert parse_entry_grams(" 125,5 ") == Decimal("125.5")
    assert parse_entry_date("11.08.2026").isoformat() == "2026-08-11"
    assert parse_entry_date("2026-08-12").isoformat() == "2026-08-12"


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1e3", "1000001"])
def test_entry_grams_reject_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        parse_entry_grams(value)


def test_local_today_uses_user_timezone() -> None:
    now = datetime(2026, 8, 10, 21, 30, tzinfo=UTC)

    assert local_today("Europe/Moscow", now).isoformat() == "2026-08-11"
    assert local_today("UTC", now).isoformat() == "2026-08-10"


async def test_diary_entry_page_is_clamped_and_uses_eight_items() -> None:
    repository = Mock()
    repository.count_by_date = AsyncMock(return_value=9)
    repository.list_by_date_page = AsyncMock(return_value=[])
    service = DiaryService(repository, Mock(), Mock(), Mock())
    entry_date = parse_entry_date("11.08.2026")

    page = await service.list_page(10, entry_date, 99)

    assert page.page == 2
    assert page.pages == 2
    repository.list_by_date_page.assert_awaited_once_with(
        10,
        entry_date,
        limit=DIARY_ENTRIES_PAGE_SIZE,
        offset=DIARY_ENTRIES_PAGE_SIZE,
    )


def test_diary_entry_keyboard_paginates_and_callbacks_fit_limit() -> None:
    entries = [
        DiaryEntry(
            id=index,
            user_id=1,
            source_name=f"Запись {index}",
            grams=Decimal("100"),
            kcal_snapshot=Decimal("150"),
        )
        for index in range(1, 9)
    ]
    page = DiaryEntryPage(items=entries, page=1, pages=2, total=9)

    keyboard = build_entry_list_keyboard(page)
    callback_data = DiaryEntryCallback(
        action="delete_confirm",
        entry_id=9_223_372_036_854_775_807,
        page=999_999,
    ).pack()

    assert len(keyboard.inline_keyboard) == 10
    assert len(callback_data.encode()) <= 64


async def test_finish_food_add_opens_today_by_default() -> None:
    message = AsyncMock()
    state = AsyncMock()
    service = AsyncMock()
    user = User(
        id=10,
        telegram_id=100,
        timezone="Europe/Moscow",
        after_food_add_action=AfterFoodAddAction.OPEN_TODAY,
    )
    expected_date = datetime(2026, 8, 15, tzinfo=UTC).date()

    with (
        patch(
            "app.bot.handlers.diary.local_today",
            return_value=expected_date,
        ),
        patch(
            "app.bot.handlers.diary.show_day",
            new_callable=AsyncMock,
        ) as show_day,
    ):
        await finish_food_add(message, state, service, user)

    show_day.assert_awaited_once_with(
        message,
        state,
        service,
        user.id,
        expected_date,
        edit=True,
    )


async def test_finish_food_add_can_stay_in_add_section() -> None:
    message = AsyncMock()
    state = AsyncMock()
    user = User(
        id=10,
        telegram_id=100,
        timezone="Europe/Moscow",
        after_food_add_action=AfterFoodAddAction.STAY,
    )

    await finish_food_add(message, state, AsyncMock(), user)

    state.clear.assert_awaited_once()
    assert "Еда добавлена" in message.edit_text.await_args.args[0]
