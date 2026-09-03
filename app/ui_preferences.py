from enum import StrEnum


class ThemeMode(StrEnum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class DefaultSection(StrEnum):
    RATION = "ration"
    FOOD = "food"
    WEIGHT = "weight"
    PROFILE = "profile"


class WeightUnit(StrEnum):
    KG = "kg"
