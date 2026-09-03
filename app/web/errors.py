import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import (
    DuplicateError,
    IdempotencyConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)


class WebAPIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers


class AuthenticationError(WebAPIError):
    def __init__(self, message: str = "Telegram authorization is invalid") -> None:
        super().__init__(
            "authentication_failed",
            message,
            status_code=401,
            headers={"WWW-Authenticate": "tma"},
        )


def error_body(
    request: Request,
    code: str,
    message: str,
    *,
    field_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "correlation_id": getattr(request.state, "correlation_id", None),
    }
    if field_errors:
        error["field_errors"] = field_errors
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency_conflict(
        request: Request,
        error: IdempotencyConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, "idempotency_conflict", str(error)),
            status_code=409,
        )

    @app.exception_handler(WebAPIError)
    async def handle_web_api_error(
        request: Request,
        error: WebAPIError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, error.code, error.message),
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.exception_handler(ValidationError)
    async def handle_domain_validation(
        request: Request,
        error: ValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, "validation_error", str(error)),
            status_code=422,
        )

    @app.exception_handler(NotFoundError)
    async def handle_domain_not_found(
        request: Request,
        error: NotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, "not_found", str(error)),
            status_code=404,
        )

    @app.exception_handler(PermissionDeniedError)
    async def handle_domain_permission_denied(
        request: Request,
        error: PermissionDeniedError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, "permission_denied", str(error)),
            status_code=403,
        )

    @app.exception_handler(DuplicateError)
    async def handle_domain_conflict(
        request: Request,
        error: DuplicateError,
    ) -> JSONResponse:
        return JSONResponse(
            error_body(request, "conflict", str(error)),
            status_code=409,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        field_errors = {
            ".".join(str(part) for part in item["loc"]): item["msg"]
            for item in error.errors()
        }
        return JSONResponse(
            error_body(
                request,
                "validation_error",
                "Проверьте введенные данные",
                field_errors=field_errors,
            ),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        code = "not_found" if error.status_code == 404 else "http_error"
        message = "Ресурс не найден" if error.status_code == 404 else str(error.detail)
        return JSONResponse(
            error_body(request, code, message),
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled Web API error",
            extra={
                "operation": "web.request",
                "exception_type": type(error).__name__,
            },
        )
        return JSONResponse(
            error_body(
                request,
                "internal_error",
                "Внутренняя ошибка сервера",
            ),
            status_code=500,
        )
