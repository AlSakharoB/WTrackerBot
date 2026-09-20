import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.services.admin_notifications import AdminNotificationService

logger = logging.getLogger(__name__)


class MiniAppReadinessError(RuntimeError):
    """Raised after repeated failures of the internal Web API readiness probe."""


@dataclass(frozen=True, slots=True)
class MiniAppReadinessStats:
    consecutive_failures: int
    incident_active: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None


class MiniAppReadinessMonitor:
    def __init__(
        self,
        notification_service: AdminNotificationService,
        *,
        url: str,
        expected_version: str,
        interval_seconds: int,
        failure_threshold: int,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._notification_service = notification_service
        self._url = url
        self._expected_version = expected_version
        self._interval_seconds = interval_seconds
        self._failure_threshold = failure_threshold
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=transport,
        )
        self._stop_event = asyncio.Event()
        self._consecutive_failures = 0
        self._incident_active = False
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None

    @property
    def stats(self) -> MiniAppReadinessStats:
        return MiniAppReadinessStats(
            consecutive_failures=self._consecutive_failures,
            incident_active=self._incident_active,
            last_success_at=self._last_success_at,
            last_failure_at=self._last_failure_at,
        )

    async def run(self) -> None:
        while not self._stop_event.is_set():
            await self.check_once()
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                continue

    async def check_once(self) -> bool:
        try:
            response = await self._client.get(
                self._url,
                headers={"Accept": "application/json"},
            )
            payload = response.json()
            if (
                response.status_code != 200
                or payload.get("status") != "ok"
                or payload.get("version") != self._expected_version
            ):
                raise MiniAppReadinessError("Web API readiness response is invalid")
        except Exception as error:
            if self._stop_event.is_set():
                return False
            await self._record_failure(error)
            return False

        recovered = self._incident_active
        self._consecutive_failures = 0
        self._incident_active = False
        self._last_success_at = datetime.now(UTC)
        if recovered:
            logger.info(
                "Mini App readiness recovered",
                extra={"operation": "miniapp.readiness_monitor"},
            )
        return True

    async def shutdown(self) -> None:
        self._stop_event.set()
        await self._client.aclose()

    async def _record_failure(self, error: Exception) -> None:
        self._consecutive_failures += 1
        self._last_failure_at = datetime.now(UTC)
        logger.warning(
            "Mini App readiness probe failed consecutive_failures=%d",
            self._consecutive_failures,
            extra={
                "operation": "miniapp.readiness_monitor",
                "exception_type": type(error).__name__,
            },
        )
        if (
            self._consecutive_failures < self._failure_threshold
            or self._incident_active
        ):
            return

        self._incident_active = True
        alert = MiniAppReadinessError(
            "Mini App Web API failed repeated internal readiness checks"
        )
        await self._notification_service.notify_error(
            alert,
            correlation_id=None,
            operation="miniapp.readiness",
            user_id=None,
        )
