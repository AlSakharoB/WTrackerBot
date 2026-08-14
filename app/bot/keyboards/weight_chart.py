from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.weights import WEIGHT_CHART, WEIGHT_MENU


class WeightChartPeriodCallback(CallbackData, prefix="wch"):
    days: int


def build_weight_chart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="7 дней",
                    callback_data=WeightChartPeriodCallback(days=7).pack(),
                ),
                InlineKeyboardButton(
                    text="30 дней",
                    callback_data=WeightChartPeriodCallback(days=30).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="90 дней",
                    callback_data=WeightChartPeriodCallback(days=90).pack(),
                ),
                InlineKeyboardButton(
                    text="180 дней",
                    callback_data=WeightChartPeriodCallback(days=180).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="1 год",
                    callback_data=WeightChartPeriodCallback(days=365).pack(),
                ),
                InlineKeyboardButton(
                    text="📅 Выбрать даты",
                    callback_data=WeightChartPeriodCallback(days=0).pack(),
                ),
            ],
            [InlineKeyboardButton(text="⬅️ К весу", callback_data=WEIGHT_MENU)],
        ]
    )


def build_weight_chart_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=WEIGHT_CHART)]
        ]
    )
