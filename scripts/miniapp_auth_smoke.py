import argparse
import getpass
import json
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol
from urllib.parse import urljoin, urlparse


class _Response(Protocol):
    status: int

    def read(self, amount: int = -1) -> bytes: ...

    def __enter__(self) -> "_Response": ...

    def __exit__(self, *args: object) -> None: ...


OpenRequest = Callable[..., _Response]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


def run_auth_smoke(
    public_url: str,
    init_data: str,
    *,
    timeout_seconds: float = 15,
    open_request: OpenRequest | None = None,
) -> str:
    parsed = urlparse(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("public URL must be an HTTPS origin")
    if not init_data:
        raise ValueError("Telegram initData must not be empty")

    request = urllib.request.Request(
        urljoin(public_url.rstrip("/") + "/", "api/v1/me"),
        headers={
            "Accept": "application/json",
            "Authorization": f"tma {init_data}",
        },
    )
    opener = (
        open_request
        or urllib.request.build_opener(
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        ).open
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read(16_385)
            status = response.status
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as error:
        raise RuntimeError("authenticated Mini App request failed") from error

    if status != 200 or len(body) > 16_384:
        raise RuntimeError(f"authenticated Mini App returned HTTP {status}")
    try:
        payload = json.loads(body)
        version = payload["app_version"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuntimeError("authenticated Mini App returned invalid JSON") from error
    if not isinstance(version, str) or not version:
        raise RuntimeError("authenticated Mini App returned an invalid version")
    return version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an authenticated Mini App smoke without storing initData",
    )
    parser.add_argument("public_url", help="production HTTPS origin")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_data = getpass.getpass("Paste fresh Telegram initData (input hidden): ")
    try:
        version = run_auth_smoke(args.public_url, init_data)
    finally:
        init_data = ""
    print(f"Authenticated Mini App smoke passed (release {version}).")


if __name__ == "__main__":
    main()
