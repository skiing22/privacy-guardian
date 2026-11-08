"""FastAPI entry point."""

from fastapi import FastAPI

from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness check used by Docker and the host."""
    return {"status": "ok", "version": app.version}
