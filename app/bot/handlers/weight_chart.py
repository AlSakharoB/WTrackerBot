import asyncio
from datetime import date

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.weight_chart import (
    WEIGHT_CHART,
    WeightChartPeriodCallback,
    build_weight_chart_cancel_keyboard,
    build_weight_chart_keyboard,
)
from app.bot.states.weights import WeightChartStates
from app.db.models.user import User
from app.exceptions import ValidationError
from app.repositories.goals import GoalRepository
from app.repositories.weights import WeightRepository
from app.services.weight_chart import (
    WeightChartData,
    WeightChartRange,
    WeightChartService,
    custom_chart_range,
    fixed_chart_range,
    parse_chart_date,
)
from app.utils.charts import render_weight_chart
from app.utils.datetime import local_today
from app.utils.decimal import format_decimal
from app.utils.formatting import format_signed_decimal

router = Router(name=__name__)


def weight_chart_service(session: AsyncSession) -> WeightChartService:
    return WeightChartService(
        WeightRepository(session),
        GoalRepository(session),
    )


def weight_chart_caption(data: WeightChartData) -> str:
    first = data.first
    last = data.last
    change = data.change_kg
    minimum = data.minimum_kg
    maximum = data.maximum_kg
    if (
        first is None
        or last is None
        or change is None
        or minimum is None
        or maximum is None
    ):
        return "За выбранный период измерений веса нет."
    return "\n".join(
        [
            f"📈 <b>Динамика веса · {data.period.label}</b>",
            "",
            f"Первый: <b>{format_decimal(first.weight_kg)} кг</b>",
            f"Последний: <b>{format_decimal(last.weight_kg)} кг</b>",
            f"Изменение: <b>{format_signed_decimal(change)} кг</b>",
            f"Минимум: {format_decimal(minimum)} кг",
            f"Максимум: {format_decimal(maximum)} кг",
        ]
    )


async def replace_with_text(
    message: Message,
    text: str,
    *,
    reply_markup: object,
) -> None:
    if message.photo:
        await message.delete()
        await message.answer(text, reply_markup=reply_markup)
    else:
        await message.edit_text(text, reply_markup=reply_markup)


async def show_weight_chart_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await replace_with_text(
        message,
        "📈 <b>График веса</b>\n\nВыберите период:",
        reply_markup=build_weight_chart_keyboard(),
    )


async def send_weight_chart(
    message: Message,
    *,
    service: WeightChartService,
    user: User,
    period: WeightChartRange,
    replace_message: bool,
) -> None:
    data = await service.get_data(
        user_id=user.id,
        period=period,
        timezone_name=user.timezone,
    )
    if not data.points:
        text = (
            f"📈 <b>Динамика веса · {period.label}</b>\n\n"
            "За выбранный период измерений веса нет."
        )
        if replace_message:
            await replace_with_text(
                message,
                text,
                reply_markup=build_weight_chart_keyboard(),
            )
        else:
            await message.answer(text, reply_markup=build_weight_chart_keyboard())
        return

    image = await asyncio.to_thread(render_weight_chart, data)
    try:
        await message.answer_photo(
            BufferedInputFile(image.getvalue(), filename="weight-chart.png"),
            caption=weight_chart_caption(data),
            reply_markup=build_weight_chart_keyboard(),
        )
    finally:
        image.close()
    if replace_message:
        await message.delete()


@router.callback_query(F.data == WEIGHT_CHART)
async def weight_chart_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.message is not None:
        await show_weight_chart_menu(callback.message, state)


@router.callback_query(WeightChartPeriodCallback.filter())
async def weight_chart_period_callback(
    callback: CallbackQuery,
    callback_data: WeightChartPeriodCallback,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    await callback.answer("Строю график…")
    if callback.message is None:
        return
    if callback_data.days == 0:
        await state.clear()
        await state.set_state(WeightChartStates.wait_date_from)
        await replace_with_text(
            callback.message,
            "Введите начальную дату в формате ДД.ММ.ГГГГ:",
            reply_markup=build_weight_chart_cancel_keyboard(),
        )
        return
    try:
        period = fixed_chart_range(
            callback_data.days,
            local_today(current_user.timezone),
        )
    except ValidationError as error:
        await callback.message.answer(str(error))
        return
    await state.clear()
    await send_weight_chart(
        callback.message,
        service=weight_chart_service(db_session),
        user=current_user,
        period=period,
        replace_message=True,
    )


@router.message(WeightChartStates.wait_date_from)
async def weight_chart_date_from_message(
    message: Message,
    state: FSMContext,
) -> None:
    try:
        date_from = parse_chart_date(message.text or "")
    except ValidationError as error:
        await message.answer(
            str(error),
            reply_markup=build_weight_chart_cancel_keyboard(),
        )
        return
    await state.update_data(weight_chart_date_from=date_from.isoformat())
    await state.set_state(WeightChartStates.wait_date_to)
    await message.answer(
        "Введите конечную дату в формате ДД.ММ.ГГГГ:\nМаксимальный период — 365 дней.",
        reply_markup=build_weight_chart_cancel_keyboard(),
    )


@router.message(WeightChartStates.wait_date_to)
async def weight_chart_date_to_message(
    message: Message,
    state: FSMContext,
    current_user: User,
    db_session: AsyncSession,
) -> None:
    try:
        date_to = parse_chart_date(message.text or "")
        state_data = await state.get_data()
        date_from = date.fromisoformat(str(state_data["weight_chart_date_from"]))
        period = custom_chart_range(date_from, date_to)
    except ValidationError as error:
        await message.answer(
            str(error),
            reply_markup=build_weight_chart_cancel_keyboard(),
        )
        return
    except (KeyError, ValueError):
        await state.clear()
        await message.answer("Данные устарели. Выберите период заново.")
        return
    await state.clear()
    await send_weight_chart(
        message,
        service=weight_chart_service(db_session),
        user=current_user,
        period=period,
        replace_message=False,
    )
