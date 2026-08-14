from enum import StrEnum


class NumberFormat(StrEnum):
    AUTOMATIC = "automatic"
    ONE_DECIMAL = "one_decimal"
    TWO_DECIMALS = "two_decimals"


class AfterFoodAddAction(StrEnum):
    OPEN_TODAY = "open_today"
    STAY = "stay"
