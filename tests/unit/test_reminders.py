from datetime import UTC, datetime, time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.bot.handlers.reminders import reminders_text
from app.bot.keyboards.reminders import (
    build_reminder_notification_keyboard,
    build_reminders_menu_keyboard,
    build_weekdays_keyboard,
)
from app.db.models.reminder import ReminderSetting, ReminderType
from app.db.models.user import User
from app.exceptions import ValidationError
from app.repositories.reminders import ReminderRecord
from app.services.reminder_scheduler import ReminderScheduler
from app.services.reminders import (
    ReminderDelivery,
    ReminderService,
    format_weekdays,
    parse_reminder_time,
    toggle_weekday,
    validate_weekdays_mask,
)


def make_setting(
    reminder_type: ReminderType = ReminderType.WEIGH_IN,
    *,
    setting_id: int = 10,
    user_id: int = 7,
    enabled: bool = True,
    weekdays_mask: int = 0b0000101,
    time_local: time = time(8, 0),
) -> ReminderSetting:
    return ReminderSetting(
        id=setting_id,
        user_id=user_id,
        reminder_type=reminder_type,
        enabled=enabled,
        weekdays_mask=weekdays_mask,
        time_local=time_local,
    )


def make_service(
    *,
    record: ReminderRecord | None,
    has_weight: bool = False,
    entries: list[object] | None = None,
    goal: object | None = None,
) -> tuple[ReminderService, AsyncMock, AsyncMock]:
    reminders = AsyncMock()
    reminders.get_enabled_record.return_value = record
    weights = AsyncMock()
    weights.exists_between.return_value = has_weight
    diary = AsyncMock()
    diary.list_by_date.return_value = entries or []
    goals = AsyncMock()
    goals.get_for_date.return_value = goal
    return ReminderService(reminders, weights, diary, goals), weights, reminders


def test_time_and_weekday_validation() -> None:
    assert parse_reminder_time("7:00") == time(7, 0)
    assert parse_reminder_time("8:00") == time(8, 0)
    assert parse_reminder_time("08:05") == time(8, 5)
    assert parse_reminder_time("23:59") == time(23, 59)
    assert format_weekdays(0b1000101) == "Пн, Ср, Вс"
    assert toggle_weekday(0, 2) == 0b0000100
    assert toggle_weekday(0b0000100, 2) == 0

    for value in ("8:5", "008:00", "24:00", "7:60", "text"):
        with pytest.raises(ValidationError):
            parse_reminder_time(value)
    for mask in (0, 128):
        with pytest.raises(ValidationError):
            validate_weekdays_mask(mask)


def test_reminders_are_disabled_by_default_in_ui() -> None:
    text = reminders_text([])
    keyboard = build_reminders_menu_keyboard([])

    assert text.count("выключено") == 2
    assert all(
        "Отключить" not in (button.text or "")
        for row in keyboard.inline_keyboard
        for button in row
    )


def test_weekday_and_notification_keyboards_are_actionable() -> None:
    weekdays = build_weekdays_keyboard(ReminderType.WEIGH_IN, 0b0000101)
    assert weekdays.inline_keyboard[0][0].text == "✓ Пн"
    assert weekdays.inline_keyboard[0][1].text == "Вт"

    weigh = build_reminder_notification_keyboard(ReminderType.WEIGH_IN)
    nutrition = build_reminder_notification_keyboard(ReminderType.NUTRITION)
    assert weigh.inline_keyboard[0][0].text == "➕ Добавить вес"
    assert nutrition.inline_keyboard[0][0].text == "📅 Сегодня"


async def test_weigh_delivery_uses_timezone_and_skips_existing_weight() -> None:
    setting = make_setting(weekdays_mask=1)
    user = User(id=7, telegram_id=77, timezone="Europe/Moscow")
    record = ReminderRecord(setting=setting, user=user)
    service, weights, _ = make_service(record=record)
    now = datetime(2026, 8, 17, 5, tzinfo=UTC)

    delivery = await service.prepare_delivery(setting.id, now=now)

    assert delivery is not None
    assert delivery.telegram_id == 77
    assert "Пора взвеситься" in delivery.text
    call = weights.exists_between.await_args.kwargs
    assert call["date_from"] == datetime(2026, 8, 16, 21, tzinfo=UTC)
    assert call["date_to_exclusive"] == datetime(2026, 8, 17, 21, tzinfo=UTC)

    weights.exists_between.return_value = True
    assert await service.prepare_delivery(setting.id, now=now) is None


async def test_delivery_ignores_disabled_or_wrong_weekday() -> None:
    user = User(id=7, telegram_id=77, timezone="Europe/Moscow")
    service, _, _ = make_service(record=None)
    assert await service.prepare_delivery(10) is None

    setting = make_setting(weekdays_mask=0b0000010)
    service, _, _ = make_service(record=ReminderRecord(setting=setting, user=user))
    monday = datetime(2026, 8, 17, 5, tzinfo=UTC)
    assert await service.prepare_delivery(setting.id, now=monday) is None


async def test_nutrition_delivery_with_and_without_goal() -> None:
    setting = make_setting(ReminderType.NUTRITION, weekdays_mask=1)
    user = User(id=8, telegram_id=88, timezone="Europe/Moscow")
    entry = SimpleNamespace(
        kcal_snapshot=Decimal("1842"),
        protein_snapshot=Decimal("126"),
        fat_snapshot=Decimal("61"),
        carbs_snapshot=Decimal("184"),
    )
    goal = SimpleNamespace(
        kcal_target=Decimal("2200"),
        protein_target_g=Decimal("160"),
        fat_target_g=Decimal("70"),
        carbs_target_g=Decimal("220"),
    )
    service, _, _ = make_service(
        record=ReminderRecord(setting=setting, user=user),
        entries=[entry],
        goal=goal,
    )
    monday = datetime(2026, 8, 17, 5, tzinfo=UTC)

    delivery = await service.prepare_delivery(setting.id, now=monday)
    assert delivery is not None
    assert "1842 / 2200" in delivery.text
    assert "126 / 160" in delivery.text

    service, _, _ = make_service(
        record=ReminderRecord(setting=setting, user=user),
        goal=None,
    )
    delivery = await service.prepare_delivery(setting.id, now=monday)
    assert delivery is not None
    assert "Напоминание о дневнике" in delivery.text
    assert "доесть" not in delivery.text.lower()


async def test_scheduler_restores_jobs_with_local_timezone(monkeypatch) -> None:
    setting = make_setting(weekdays_mask=0b0000101)
    user = User(id=7, telegram_id=77, timezone="Asia/Almaty")
    context = AsyncMock()
    context.__aenter__.return_value = AsyncMock()
    session_factory = Mock(return_value=context)
    monkeypatch.setattr(
        "app.services.reminder_scheduler.ReminderRepository.list_enabled_records",
        AsyncMock(return_value=[ReminderRecord(setting=setting, user=user)]),
    )
    scheduler = ReminderScheduler(
        Mock(),
        session_factory,
        misfire_grace_seconds=1800,
    )

    await scheduler.start()
    try:
        job = scheduler._scheduler.get_job(  # noqa: SLF001
            scheduler.job_id(user.id, setting.reminder_type)
        )
        assert scheduler.running
        assert scheduler.job_count == 1
        assert job is not None
        assert scheduler.last_heartbeat is not None
        assert scheduler.next_job_time == job.next_run_time
        assert str(job.trigger.timezone) == "Asia/Almaty"
        assert job.misfire_grace_time == 1800
        assert job.coalesce
    finally:
        await scheduler.shutdown()


async def test_forbidden_disables_persisted_reminder(monkeypatch) -> None:
    setting = make_setting(weekdays_mask=1)
    delivery = ReminderDelivery(
        setting_id=setting.id,
        telegram_id=77,
        user_id=setting.user_id,
        reminder_type=setting.reminder_type,
        text="test",
    )
    bot = Mock()
    bot.send_message = AsyncMock(
        side_effect=TelegramForbiddenError(
            method=SendMessage(chat_id=77, text="test"),
            message="Forbidden",
        )
    )
    session = AsyncMock()
    transaction = AsyncMock()
    session.begin = Mock(return_value=transaction)
    context = AsyncMock()
    context.__aenter__.return_value = session
    session_factory = Mock(return_value=context)
    service = AsyncMock()
    service.prepare_delivery.return_value = delivery
    monkeypatch.setattr(
        "app.services.reminder_scheduler.ReminderScheduler._service",
        Mock(return_value=service),
    )
    disable = AsyncMock()
    monkeypatch.setattr(
        "app.services.reminder_scheduler.ReminderRepository.disable_by_id",
        disable,
    )
    scheduler = ReminderScheduler(
        bot,
        session_factory,
        misfire_grace_seconds=1800,
    )
    scheduler.schedule(setting, "Europe/Moscow")

    await scheduler.run_job(setting.id)

    bot.send_message.assert_awaited_once()
    disable.assert_awaited_once_with(setting.id)
    assert scheduler.job_count == 0
