import re
from urllib.parse import urlencode

from app.sharing.tokens import is_valid_share_token

BOT_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def normalize_bot_username(bot_username: str) -> str:
    username = bot_username.strip().removeprefix("@")
    if BOT_USERNAME_PATTERN.fullmatch(username) is None:
        raise ValueError("Invalid bot username")
    return username


def build_share_deep_link(bot_username: str, token: str) -> str:
    username = normalize_bot_username(bot_username)
    if not is_valid_share_token(token):
        raise ValueError("Invalid share token")
    return f"https://t.me/{username}?{urlencode({'start': token})}"


def build_telegram_share_url(deep_link: str, text: str) -> str:
    if not deep_link.startswith("https://t.me/"):
        raise ValueError("Only Telegram deep links can be shared")
    return f"https://t.me/share/url?{urlencode({'url': deep_link, 'text': text})}"
