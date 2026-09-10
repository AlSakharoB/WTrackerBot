from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from app.exceptions import ValidationError

SUPPORTED_GTIN_LENGTHS = {8, 12, 13, 14}
OFF_IMAGE_HOSTS = {"images.openfoodfacts.org", "static.openfoodfacts.org"}


def normalize_gtin(value: str) -> str:
    barcode = "".join(character for character in value if not character.isspace())
    if (
        len(barcode) not in SUPPORTED_GTIN_LENGTHS
        or not barcode.isascii()
        or not barcode.isdigit()
    ):
        raise ValidationError("Введите корректный EAN-8, UPC-A, EAN-13 или GTIN-14.")
    expected = (
        10
        - sum(
            int(digit) * (3 if index % 2 == 0 else 1)
            for index, digit in enumerate(reversed(barcode[:-1]))
        )
        % 10
    ) % 10
    if expected != int(barcode[-1]):
        raise ValidationError("Контрольная цифра штрихкода не совпадает.")
    return barcode


def decimal_value(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    normalized = str(value).strip().replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation:
        return None
    return result if result.is_finite() and result >= 0 else None


def safe_off_image_url(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 2048:
        return None
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in OFF_IMAGE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    return value
