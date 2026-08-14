from contextvars import ContextVar, Token
from decimal import ROUND_HALF_UP, Decimal

from app.user_settings import NumberFormat

_number_format: ContextVar[NumberFormat] = ContextVar(
    "number_format",
    default=NumberFormat.AUTOMATIC,
)


def set_number_format(value: NumberFormat) -> Token[NumberFormat]:
    return _number_format.set(value)


def reset_number_format(token: Token[NumberFormat]) -> None:
    _number_format.reset(token)


def format_decimal(value: Decimal, decimal_places: int | None = None) -> str:
    if decimal_places is None:
        selected = _number_format.get()
        decimal_places = {
            NumberFormat.AUTOMATIC: 2,
            NumberFormat.ONE_DECIMAL: 1,
            NumberFormat.TWO_DECIMALS: 2,
        }[selected]
        keep_trailing_zeroes = selected is not NumberFormat.AUTOMATIC
    else:
        keep_trailing_zeroes = False
    quantum = Decimal(1).scaleb(-decimal_places)
    formatted = format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    if keep_trailing_zeroes:
        return formatted
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
