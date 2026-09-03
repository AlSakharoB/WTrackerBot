import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest

from app.web.auth import TelegramInitDataError, TelegramInitDataValidator

BOT_TOKEN = "123456:test-secret-token"
NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def sign_init_data(
    *,
    user: dict[str, object] | None = None,
    auth_date: datetime = NOW,
    extra: list[tuple[str, str]] | None = None,
) -> str:
    fields = [
        ("auth_date", str(int(auth_date.timestamp()))),
        ("query_id", "AAHdF6IQAAAAAN0XohDhrOrc"),
        (
            "user",
            json.dumps(
                user
                or {
                    "id": 279058397,
                    "first_name": "Vladislav",
                    "last_name": "Sakharov",
                    "username": "example_user",
                    "language_code": "ru",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    ]
    fields.extend(extra or [])
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields))
    secret_key = hmac.digest(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256)
    signature = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return urlencode([*fields, ("hash", signature)])


def make_validator() -> TelegramInitDataValidator:
    return TelegramInitDataValidator(
        BOT_TOKEN,
        max_age_seconds=300,
        clock_skew_seconds=30,
    )


def test_validate_signed_init_data() -> None:
    result = make_validator().validate(sign_init_data(), now=NOW)

    assert result.user.id == 279058397
    assert result.user.first_name == "Vladislav"
    assert result.auth_date == NOW
    assert result.query_id == "AAHdF6IQAAAAAN0XohDhrOrc"


def test_reject_tampered_user() -> None:
    raw = sign_init_data().replace("279058397", "999999999")

    with pytest.raises(TelegramInitDataError, match="signature"):
        make_validator().validate(raw, now=NOW)


@pytest.mark.parametrize(
    ("auth_date", "message"),
    [
        (NOW - timedelta(seconds=301), "expired"),
        (NOW + timedelta(seconds=31), "future"),
    ],
)
def test_reject_init_data_outside_time_window(
    auth_date: datetime,
    message: str,
) -> None:
    with pytest.raises(TelegramInitDataError, match=message):
        make_validator().validate(sign_init_data(auth_date=auth_date), now=NOW)


def test_accept_configured_clock_skew() -> None:
    result = make_validator().validate(
        sign_init_data(auth_date=NOW + timedelta(seconds=30)),
        now=NOW,
    )

    assert result.user.id == 279058397


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "auth_date",
        "auth_date=1&user=%ZZ&hash=" + "a" * 64,
        "auth_date=1&auth_date=2&hash=" + "a" * 64,
        "auth_date=1&hash=invalid",
    ],
)
def test_reject_malformed_init_data(raw: str) -> None:
    with pytest.raises(TelegramInitDataError):
        make_validator().validate(raw, now=NOW)


def test_reject_duplicate_signed_field() -> None:
    raw = sign_init_data(extra=[("query_id", "duplicate")])

    with pytest.raises(TelegramInitDataError, match="Duplicate"):
        make_validator().validate(raw, now=NOW)


def test_reject_invalid_signed_user_payload() -> None:
    raw = sign_init_data(user={"id": -1, "first_name": ""})

    with pytest.raises(TelegramInitDataError, match="user"):
        make_validator().validate(raw, now=NOW)
