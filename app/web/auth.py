import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_HASH_PATTERN = re.compile(r"[0-9A-Fa-f]{64}\Z")
_MAX_FIELDS = 64


class TelegramWebAppUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int = Field(gt=0, strict=True)
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    language_code: str | None = Field(default=None, max_length=35)
    is_premium: bool | None = None
    allows_write_to_pm: bool | None = None
    photo_url: str | None = Field(default=None, max_length=2048)


@dataclass(frozen=True, slots=True)
class ValidatedInitData:
    user: TelegramWebAppUser
    auth_date: datetime
    query_id: str | None
    start_param: str | None


class TelegramInitDataError(ValueError):
    """Raised when Telegram Mini App authorization data cannot be trusted."""


class TelegramInitDataValidator:
    def __init__(
        self,
        bot_token: str,
        *,
        max_age_seconds: int,
        clock_skew_seconds: int,
    ) -> None:
        self._bot_token = bot_token.encode()
        self._max_age_seconds = max_age_seconds
        self._clock_skew_seconds = clock_skew_seconds

    def validate(
        self,
        raw_init_data: str,
        *,
        now: datetime | None = None,
    ) -> ValidatedInitData:
        if not raw_init_data or _INVALID_PERCENT_ESCAPE.search(raw_init_data):
            raise TelegramInitDataError("Malformed Telegram initData")

        try:
            pairs = parse_qsl(
                raw_init_data,
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=_MAX_FIELDS,
            )
        except (ValueError, UnicodeError) as error:
            raise TelegramInitDataError("Malformed Telegram initData") from error

        values: dict[str, str] = {}
        for key, value in pairs:
            if not key or key in values:
                raise TelegramInitDataError("Duplicate Telegram initData field")
            values[key] = value

        received_hash = values.pop("hash", None)
        if received_hash is None or _HASH_PATTERN.fullmatch(received_hash) is None:
            raise TelegramInitDataError("Invalid Telegram initData hash")

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(values.items())
        )
        secret_key = hmac.digest(b"WebAppData", self._bot_token, hashlib.sha256)
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash.lower()):
            raise TelegramInitDataError("Invalid Telegram initData signature")

        auth_date = self._parse_auth_date(values.get("auth_date"), now=now)
        raw_user = values.get("user")
        if raw_user is None:
            raise TelegramInitDataError("Telegram initData has no user")
        try:
            user = TelegramWebAppUser.model_validate(json.loads(raw_user))
        except (json.JSONDecodeError, ValidationError, TypeError) as error:
            raise TelegramInitDataError("Invalid Telegram user data") from error

        return ValidatedInitData(
            user=user,
            auth_date=auth_date,
            query_id=values.get("query_id"),
            start_param=values.get("start_param"),
        )

    def _parse_auth_date(
        self,
        raw_auth_date: str | None,
        *,
        now: datetime | None,
    ) -> datetime:
        try:
            timestamp = int(raw_auth_date or "")
            auth_date = datetime.fromtimestamp(timestamp, UTC)
        except (ValueError, OverflowError, OSError) as error:
            raise TelegramInitDataError("Invalid Telegram auth_date") from error

        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        else:
            current = current.astimezone(UTC)
        age_seconds = (current - auth_date).total_seconds()
        if age_seconds < -self._clock_skew_seconds:
            raise TelegramInitDataError("Telegram initData is from the future")
        if age_seconds > self._max_age_seconds:
            raise TelegramInitDataError("Telegram initData has expired")
        return auth_date
