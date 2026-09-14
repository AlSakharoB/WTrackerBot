import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Literal

HealthMode = Literal["liveness", "readiness"]


def check_web_health(
    *,
    mode: HealthMode,
    port: int,
    timeout_seconds: float,
) -> None:
    endpoint = "healthz" if mode == "liveness" else "readyz"
    url = f"http://127.0.0.1:{port}/internal/{endpoint}"
    request = urllib.request.Request(  # noqa: S310 - fixed loopback URL
        url,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
            request,
            timeout=timeout_seconds,
        ) as response:
            body = response.read(4097)
            status_code = response.status
    except (OSError, urllib.error.HTTPError, urllib.error.URLError) as error:
        raise RuntimeError(f"Web {mode} request failed") from error

    if status_code != 200 or len(body) > 4096:
        raise RuntimeError(f"Web {mode} returned an invalid response")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Web {mode} returned invalid JSON") from error
    if payload.get("status") != "ok":
        raise RuntimeError(f"Web {mode} status is not ok")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check the internal Mini App API")
    parser.add_argument(
        "--mode",
        choices=("liveness", "readiness"),
        default="liveness",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    port = int(os.environ.get("MINIAPP_PORT", "8080"))
    timeout_seconds = float(os.environ.get("WEB_HEALTHCHECK_TIMEOUT_SECONDS", "3"))
    check_web_health(
        mode=args.mode,
        port=port,
        timeout_seconds=timeout_seconds,
    )


if __name__ == "__main__":
    main()
