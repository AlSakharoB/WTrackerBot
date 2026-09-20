from unittest.mock import AsyncMock, Mock

import httpx

from app.services.miniapp_readiness import MiniAppReadinessMonitor


def response(status: int, payload: dict[str, str]) -> httpx.Response:
    return httpx.Response(status, json=payload)


async def test_readiness_monitor_notifies_once_per_incident_and_recovers() -> None:
    responses = iter(
        (
            response(503, {"status": "error", "version": "1.0.6"}),
            response(503, {"status": "error", "version": "1.0.6"}),
            response(503, {"status": "error", "version": "1.0.6"}),
            response(200, {"status": "ok", "version": "1.0.6"}),
            response(200, {"status": "ok", "version": "old"}),
            response(200, {"status": "ok", "version": "old"}),
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://web:8080/internal/readyz"
        return next(responses)

    notifier = Mock(notify_error=AsyncMock())
    monitor = MiniAppReadinessMonitor(
        notifier,
        url="http://web:8080/internal/readyz",
        expected_version="1.0.6",
        interval_seconds=60,
        failure_threshold=2,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )

    assert not await monitor.check_once()
    assert not await monitor.check_once()
    assert not await monitor.check_once()
    assert notifier.notify_error.await_count == 1
    assert monitor.stats.incident_active
    assert await monitor.check_once()
    assert not monitor.stats.incident_active
    assert monitor.stats.consecutive_failures == 0
    assert not await monitor.check_once()
    assert not await monitor.check_once()
    assert notifier.notify_error.await_count == 2
    assert all(
        call.kwargs["operation"] == "miniapp.readiness"
        for call in notifier.notify_error.await_args_list
    )

    await monitor.shutdown()


async def test_readiness_monitor_does_not_alert_during_shutdown() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unavailable")

    notifier = Mock(notify_error=AsyncMock())
    monitor = MiniAppReadinessMonitor(
        notifier,
        url="http://web:8080/internal/readyz",
        expected_version="1.0.6",
        interval_seconds=60,
        failure_threshold=1,
        timeout_seconds=3,
        transport=httpx.MockTransport(handler),
    )
    await monitor.shutdown()

    assert not await monitor.check_once()
    notifier.notify_error.assert_not_awaited()
