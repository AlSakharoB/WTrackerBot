import hashlib
import re
import secrets

SHARE_TOKEN_BYTES = 24
SHARE_TOKEN_PREFIX = "sh_"
SHARE_TOKEN_PATTERN = re.compile(r"^sh_[A-Za-z0-9_-]{32}$")
TELEGRAM_START_PARAMETER_MAX_LENGTH = 64


def generate_share_token() -> str:
    """Return an opaque token with 192 bits of CSPRNG entropy."""
    token = f"{SHARE_TOKEN_PREFIX}{secrets.token_urlsafe(SHARE_TOKEN_BYTES)}"
    if not is_valid_share_token(token):  # pragma: no cover - defensive invariant
        raise RuntimeError("Generated share token has an invalid format")
    return token


def is_valid_share_token(token: str) -> bool:
    return (
        len(token) <= TELEGRAM_START_PARAMETER_MAX_LENGTH
        and SHARE_TOKEN_PATTERN.fullmatch(token) is not None
    )


def hash_share_token(token: str) -> str:
    if not is_valid_share_token(token):
        raise ValueError("Invalid share token")
    return hashlib.sha256(token.encode("ascii")).hexdigest()
