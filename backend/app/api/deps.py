"""FastAPI dependencies: the container, the current user, role checks, client IP."""

from typing import Annotated

from fastapi import Depends, Request

from app.services.auth import UserRow, session_hash
from app.services.container import Container
from app.services.errors import AppError

COOKIE = "pg_session"
GENERAL_LIMIT = (120, 60.0)


def container(request: Request) -> Container:
    c: Container = request.app.state.container
    return c


Box = Annotated[Container, Depends(container)]


def client_ip(request: Request) -> str:
    """Socket address, or X-Forwarded-For only when a trusted proxy is in front (API 7)."""
    c = container(request)
    n = c.settings.trusted_proxy_count
    if n > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p]
        if len(chain) >= n:
            return chain[-n]
    return request.client.host if request.client else "unknown"


def _user(request: Request, c: Container) -> UserRow:
    token = request.cookies.get(COOKIE)
    user = c.auth.current(token)
    request.state.user_id = user.id
    request.state.session_key = session_hash(token or "").hex()[:16]
    return user


def user_unlimited(request: Request, c: Box) -> UserRow:
    """Logged in; the caller applies the general limit itself (status polling)."""
    return _user(request, c)


def current_user(request: Request, c: Box) -> UserRow:
    user = _user(request, c)
    c.limiter.hit(f"general:{request.state.session_key}", *GENERAL_LIMIT)
    return user


def admin_user(user: Annotated[UserRow, Depends(current_user)]) -> UserRow:
    if user.role != "admin":
        raise AppError("forbidden")
    return user


User = Annotated[UserRow, Depends(current_user)]
UserNoLimit = Annotated[UserRow, Depends(user_unlimited)]
Admin = Annotated[UserRow, Depends(admin_user)]
