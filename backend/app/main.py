"""FastAPI app factory (ARCHITECTURE 3, API.md 1).

Serves the JSON API under /api/v1, /health, and the built React app from the same origin.
Startup: migrate the database (with a backup), build the container, create the first admin
from ADMIN_EMAIL/ADMIN_PASSWORD if there are no users yet, start the background threads.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api import errors as api_errors
from app.api import middleware
from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_scans import router as scans_router
from app.api.schemas import Health
from app.config import Settings, check_prod, get_settings, load_keyring
from app.graph.build import Detector
from app.log import configure_logging
from app.runtime.worker import Runtime
from app.services.container import Container
from app.storage.db import migrate

log = logging.getLogger("app.main")

try:
    APP_VERSION = version("privacy-guardian")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled tree
    APP_VERSION = "0.0.0"


def bootstrap_admin(c: Container) -> None:
    s = c.settings
    if s.admin_email and s.admin_password and c.auth.users.count() == 0:
        c.auth.create_user(s.admin_email, s.admin_password.get_secret_value(), "admin")
        log.info("first admin created", extra={"event": "admin_bootstrap"})


def create_app(
    settings: Settings | None = None,
    *,
    detectors: dict[str, Detector] | None = None,
    start_threads: bool = True,
) -> FastAPI:
    """`detectors` lets tests inject a fake NER; `start_threads=False` lets tests drive the
    worker themselves."""
    settings = settings or get_settings()
    check_prod(settings)
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        ring, app.state.dev_keys = load_keyring(settings)
        migrate(settings.data_dir)
        c = Container.build(settings, ring)
        c.detectors = detectors
        app.state.container = c
        bootstrap_admin(c)
        runtime = Runtime(c)
        app.state.runtime = runtime
        if start_threads:
            runtime.start()
        try:
            yield
        finally:
            runtime.shutdown()
            c.close()

    is_prod = settings.env == "prod"
    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/openapi.json",
    )

    api_errors.install(app)
    middleware.install(app, settings)

    @app.get(
        "/health",
        tags=["health"],
        response_model=Health,
        responses={503: {"model": Health, "description": "Model not ready"}},
    )
    def health(request: Request) -> Health | JSONResponse:
        """Liveness + model readiness (API 4.1): 503 while the model loads."""
        c: Container | None = getattr(request.app.state, "container", None)
        if c is not None and c.model_ready.is_set():
            return Health(status="ok", model_ready=True, version=APP_VERSION)
        body = {
            "status": "starting", "model_ready": False, "version": APP_VERSION,
            "error": {"code": "model_not_ready", "message": "Preparing the model.",
                      "field": None, "request_id": getattr(request.state, "request_id", None)},
        }  # fmt: skip
        return JSONResponse(body, status_code=503)

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)
    api.include_router(scans_router)
    api.include_router(admin_router)
    app.include_router(api)

    @app.api_route(
        "/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False
    )
    def api_not_found(path: str, request: Request) -> JSONResponse:
        return api_errors.error_response(request, "not_found")

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
