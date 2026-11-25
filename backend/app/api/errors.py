"""One error format for every non-2xx response (API 2.3). Messages are fixed strings or
Pydantic's rule text; the offending input value is never echoed back."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import MESSAGES, AppError, storage_error_code

log = logging.getLogger("app.api")


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(
    request: Request, code: str, message: str | None = None, field: str | None = None,
    headers: dict[str, str] | None = None, status: int | None = None,
) -> JSONResponse:  # fmt: skip
    st, default = MESSAGES[code]
    rid = request_id(request)
    msg = message or default.format(request_id=rid or "-", n="", mb="")
    body = {"error": {"code": code, "message": msg, "field": field, "request_id": rid}}
    return JSONResponse(body, status_code=status or st, headers=headers)


def _field(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "form")]
    return ".".join(parts) or None


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(request, exc.code, exc.message, exc.field, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        msg = str(first.get("msg", "Invalid request.")).removeprefix("Value error, ")
        if first.get("type") == "extra_forbidden":
            msg = "Unknown field."
        return error_response(request, "invalid_request", msg, _field(tuple(first.get("loc", ()))))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response(request, "not_found")
        if exc.status_code == 405:
            return error_response(request, "not_found", "Not found.", status=405)
        if exc.status_code == 413:  # the app's body limit (main.py)
            mb = request.app.state.container.settings.max_upload_mb
            return error_response(
                request, "file_too_large", f"File too large (max {mb} MB).", "file"
            )
        return error_response(request, "invalid_request", status=exc.status_code)

    @app.exception_handler(Exception)
    async def internal(request: Request, exc: Exception) -> JSONResponse:
        code = storage_error_code(exc)
        if code == "busy":
            return error_response(request, code, headers={"Retry-After": "2"})
        log.error("request failed", extra={"error_code": type(exc).__name__})
        return error_response(request, code or "internal")
