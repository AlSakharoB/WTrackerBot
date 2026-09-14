import json
from collections.abc import Callable
from typing import Any
from urllib.error import URLError

import pytest

from scripts import web_healthcheck


class FakeResponse:
    def __init__(self, payload: dict[str, str], *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._body[:limit]


@pytest.mark.parametrize(
    ("mode", "expected_path"),
    [
        ("liveness", "/internal/healthz"),
        ("readiness", "/internal/readyz"),
    ],
)
def test_healthcheck_uses_loopback_internal_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    mode: web_healthcheck.HealthMode,
    expected_path: str,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(
        request: web_healthcheck.urllib.request.Request,
        *,
        timeout: float,
    ) -> FakeResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse({"status": "ok", "version": "1.0.2"})

    monkeypatch.setattr(web_healthcheck.urllib.request, "urlopen", fake_urlopen)

    web_healthcheck.check_web_health(
        mode=mode,
        port=8080,
        timeout_seconds=2.5,
    )

    assert captured == {
        "url": f"http://127.0.0.1:8080{expected_path}",
        "timeout": 2.5,
    }


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda: FakeResponse({"status": "error"}),
        lambda: FakeResponse({"status": "ok"}, status=503),
        lambda: FakeResponse({"message": "missing status"}),
    ],
)
def test_healthcheck_rejects_unhealthy_response(
    monkeypatch: pytest.MonkeyPatch,
    response_factory: Callable[[], FakeResponse],
) -> None:
    monkeypatch.setattr(
        web_healthcheck.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: response_factory(),
    )

    with pytest.raises(RuntimeError, match="Web readiness"):
        web_healthcheck.check_web_health(
            mode="readiness",
            port=8080,
            timeout_seconds=3,
        )


def test_healthcheck_hides_connection_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_network_error(*_args: object, **_kwargs: object) -> None:
        raise URLError("sensitive upstream detail")

    monkeypatch.setattr(
        web_healthcheck.urllib.request,
        "urlopen",
        raise_network_error,
    )

    with pytest.raises(RuntimeError, match="Web liveness request failed") as error:
        web_healthcheck.check_web_health(
            mode="liveness",
            port=8080,
            timeout_seconds=3,
        )

    assert "sensitive upstream detail" not in str(error.value)
