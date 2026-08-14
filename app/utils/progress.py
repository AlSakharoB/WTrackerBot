from decimal import Decimal


def build_progress_bar(
    progress_percent: Decimal,
    length: int = 10,
) -> str:
    if length <= 0:
        raise ValueError("Progress bar length must be positive")
    clamped = min(max(progress_percent, Decimal("0")), Decimal("100"))
    filled = int(clamped * length / Decimal("100"))
    return "█" * filled + "░" * (length - filled)
