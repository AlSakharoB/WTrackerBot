import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import Message, Receive, Scope, Send

from app.core.logging import logging_context
from app.web.errors import error_body

logger = logging.getLogger(__name__)
_CORRELATION_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        supplied = request.headers.get("X-Correlation-ID", "")
        correlation_id = (
            supplied if _CORRELATION_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        )
        request.state.correlation_id = correlation_id
        started = perf_counter()
        with logging_context(
            correlation_id=correlation_id,
            handler=f"{request.method} {request.url.path}",
            operation="web.request",
        ):
            response = await call_next(request)
            duration_ms = (perf_counter() - started) * 1000
            logger.info(
                "Web request completed method=%s path=%s status=%d duration_ms=%.1f",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={"user_id": getattr(request.state, "user_id", "-")},
            )
        response.headers["X-Correlation-ID"] = correlation_id
        return response


ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RequestLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                await JSONResponse(
                    error_body(
                        request,
                        "invalid_content_length",
                        "Invalid Content-Length header",
                    ),
                    status_code=400,
                )(scope, receive, send)
                return
            if length < 0:
                await JSONResponse(
                    error_body(
                        request,
                        "invalid_content_length",
                        "Invalid Content-Length header",
                    ),
                    status_code=400,
                )(scope, receive, send)
                return
            if length > self._max_body_bytes:
                await JSONResponse(
                    error_body(
                        request,
                        "request_too_large",
                        "Request body is too large",
                    ),
                    status_code=413,
                )(scope, receive, send)
                return

        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            await self.app(scope, receive, send)
            return

        messages: list[Message] = []
        received_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            received_bytes += len(message.get("body", b""))
            if received_bytes > self._max_body_bytes:
                await JSONResponse(
                    error_body(
                        request,
                        "request_too_large",
                        "Request body is too large",
                    ),
                    status_code=413,
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        message_iterator = iter(messages)

        async def replay_receive() -> Message:
            return next(message_iterator, {"type": "http.disconnect"})

        await self.app(scope, replay_receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response
