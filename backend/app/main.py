"""FastAPI app factory (ARCHITECTURE 3, API.md 1).

Serves the JSON API under /api/v1, /health, and the built React app from the same origin.
Routers are added per phase (IMPLEMENTATION_PLAN.md P5 onwards).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.config import Settings, check_prod, get_settings, load_keyring
from app.log import configure_logging

try:
    APP_VERSION = version("privacy-guardian")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    APP_VERSION = "0.0.0"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    check_prod(settings)
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.keyring, app.state.dev_keys = load_keyring(settings)
        app.state.model_ready = False  # set by the model loader (P7)
        yield

    is_prod = settings.env == "prod"
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )

    @app.get("/health", tags=["health"])
    def health(request: Request) -> dict[str, object]:
        """Liveness + model readiness (API.md 4.1). The 503-while-loading rule starts in P7,
        when the model loader exists."""
        ready = bool(getattr(request.app.state, "model_ready", False))
        return {"status": "ok", "model_ready": ready, "version": APP_VERSION}

    api = APIRouter(prefix="/api/v1")
    app.include_router(api)

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False
    )
    def api_not_found(path: str) -> JSONResponse:
        body = {"error": {"code": "not_found", "message": "Not found.", "field": None}}
        return JSONResponse(body, status_code=404)

    _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA: real files as-is, every other path gets index.html (client routes)."""
    index = static_dir / "index.html"
    if not index.is_file():
        return
    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and static_dir.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
