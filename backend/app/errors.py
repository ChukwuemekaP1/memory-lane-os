"""Shared error envelope + exception handlers (API_SPECIFICATION Section 2)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppError(Exception):
    """User-safe application error rendered into the standard envelope."""

    def __init__(self, code: str, message: str, status_code: int = 400,
                 retryable: bool = False, details: dict[str, Any] | None = None,
                 headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
        self.headers = headers or {}


def error_payload(exc: AppError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
            "details": exc.details,
            "request_id": request_id_ctx.get(),
        }
    }


def ok_payload(data: Any) -> dict[str, Any]:
    return {"data": data, "request_id": request_id_ctx.get()}


async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=error_payload(exc),
                        headers=exc.headers or None)


async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    fields = [{"field": ".".join(str(p) for p in err["loc"] if p != "body"),
               "reason": err["msg"]} for err in exc.errors()]
    wrapped = AppError("validation_error", "Request validation failed.",
                       status.HTTP_422_UNPROCESSABLE_CONTENT, details={"fields": fields})
    return JSONResponse(status_code=wrapped.status_code, content=error_payload(wrapped))


async def _http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {401: "unauthenticated", 403: "forbidden", 404: "not_found",
            409: "conflict", 410: "gone", 413: "payload_too_large",
            415: "unsupported_media", 429: "rate_limited"}.get(exc.status_code, "internal_error")
    status_code = exc.status_code if 400 <= exc.status_code < 500 else 500
    wrapped = AppError(code, str(exc.detail), status_code)
    return JSONResponse(status_code=status_code, content=error_payload(wrapped))


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception: %s", type(exc).__name__)
    wrapped = AppError("internal_error", "Something went wrong.", 500)
    return JSONResponse(status_code=500, content=error_payload(wrapped))


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)
