"""Endpoints 2-4: login, logout, me (API 4.2 to 4.4)."""

from fastapi import APIRouter, Request, Response

from app.api.deps import COOKIE, Box, User, client_ip
from app.api.schemas import ERR, LoginIn, Me

router = APIRouter(prefix="/auth", tags=["auth"], responses={401: ERR})


@router.post("/login", status_code=204, responses={429: ERR})
def login(body: LoginIn, request: Request, response: Response, c: Box) -> None:
    s = c.auth.login(body.email, body.password, client_ip(request), request.cookies.get(COOKIE))
    request.state.user_id = s.user.id
    response.set_cookie(
        COOKIE, s.token, max_age=c.settings.session_max_days * 86400, path="/",
        httponly=True, secure=c.settings.env == "prod", samesite="strict",
    )  # fmt: skip


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, c: Box) -> None:
    c.auth.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                           secure=c.settings.env == "prod")  # fmt: skip


@router.get("/me")
def me(user: User) -> Me:
    return Me(id=user.id, email=user.email, role=user.role)
