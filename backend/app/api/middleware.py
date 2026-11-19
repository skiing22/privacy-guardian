"""Per-request middleware (API 2.2, 3.2):
- request id (echo a valid client one, else new), on the response and in logs
- Origin check on state-changing /api requests (bad_origin)
- early 413 when Content-Length already says the upload is too big
- security headers; no-store on API and health responses
- one access log line per request: method, route template, status, duration (no query)
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api.errors import error_response
from app.config import Settings

log = logging.getLogger("app.access")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
MULTIPART_OVERHEAD = 64 * 1024


def allowed_origins(s: Settings) -> set[str]:
    out = {s.public_origin.rstrip("/")}
    if s.env == "dev":
        out.update(DEV_ORIGINS)
    return out


def _valid_uuid(v: str | None) -> bool:
    try:
        return v is not None and len(v) == 36 and bool(uuid.UUID(v))
    except ValueError:
        return False


def install(app: FastAPI, settings: Settings) -> None:
    origins = allowed_origins(settings)
    prod = settings.env == "prod"

    @app.middleware("http")
    async def per_request(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        incoming = request.headers.get("x-request-id")
        rid = incoming if incoming is not None and _valid_uuid(incoming) else str(uuid.uuid4())
        request.state.request_id = rid
        path = request.url.path
        is_api = path.startswith("/api/")

        response: Response
        if is_api and request.method in UNSAFE and request.headers.get("origin") not in origins:
            response = error_response(request, "bad_origin")
        elif (
            path == "/api/v1/scans"
            and request.method == "POST"
            and int(request.headers.get("content-length") or 0)
            > settings.max_upload_bytes + MULTIPART_OVERHEAD
        ):
            response = error_response(
                request, "file_too_large",
                f"File too large (max {settings.max_upload_mb} MB).", "file",
            )  # fmt: skip
        else:
            response = await call_next(request)

        h = response.headers
        h["X-Request-ID"] = rid
        h["X-Content-Type-Options"] = "nosniff"
        h["Referrer-Policy"] = "no-referrer"
        h.setdefault("Content-Security-Policy", CSP)
        if prod:
            h["Strict-Transport-Security"] = "max-age=31536000"
        if is_api or path == "/health":
            h["Cache-Control"] = "no-store"
        route = request.scope.get("route")
        log.info(
            "request",
            extra={
                "request_id": rid, "method": request.method,
                "route": getattr(route, "path", "static" if not is_api else "unmatched"),
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                "user_id": getattr(request.state, "user_id", None),
            },
        )  # fmt: skip
        return response
