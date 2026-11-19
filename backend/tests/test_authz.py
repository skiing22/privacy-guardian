"""Authorization matrix (ARCHITECTURE 8, 15): every API route, every kind of caller.

Routes are discovered from the app itself, so a new route added without a session or
role check fails here instead of shipping."""

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import clock
from app.services.admin import AdminService
from app.services.errors import AppError
from app.services.ratelimit import RateLimiter
from tests.api_helpers import ORIGIN, PW, Api, api

# login is public; logout is idempotent (API 4.3: 204 even with no session, so a stale tab
# can always log out). Neither returns data.
PUBLIC = {("POST", "/api/v1/auth/login"), ("POST", "/api/v1/auth/logout")}
ADMIN_ONLY_PREFIX = "/api/v1/admin/"
REVEAL = ("POST", "/api/v1/admin/reveal")  # any user may call; non-admins refused + logged


def api_routes(a: Api) -> list[tuple[str, str]]:
    """Every documented /api/v1 route. The only undocumented route is the /api 404
    catch-all, which needs no protection."""
    paths = a.http.app.openapi()["paths"]  # type: ignore[attr-defined]
    return sorted(
        (m.upper(), p) for p, ops in paths.items() if p.startswith("/api/v1/") for m in ops
    )


def call(a: Api, method: str, path: str):  # type: ignore[no-untyped-def]
    url = path.replace("{scan_id}", str(uuid.uuid4()))
    return a.http.request(method, url, headers={"Origin": ORIGIN}, json={})


def test_every_route_is_known_to_this_test(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        routes = api_routes(a)
    assert len(routes) == 18  # API.md: 19 endpoints, /health is outside /api/v1


def test_anonymous_gets_401_everywhere_but_login(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        for method, path in api_routes(a):
            if (method, path) in PUBLIC:
                continue
            r = call(a, method, path)
            assert r.status_code == 401, (method, path, r.status_code)
            assert r.json()["error"]["code"] == "auth_required"


def test_normal_user_gets_403_on_every_admin_route(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("u@x.io")
        a.login("u@x.io")
        for method, path in api_routes(a):
            if not path.startswith(ADMIN_ONLY_PREFIX) or (method, path) == REVEAL:
                continue
            r = call(a, method, path)
            assert r.status_code == 403, (method, path, r.status_code)
        # reveal: refused too, after validation and with an audit record
        r = a.post("/api/v1/admin/reveal", json={"token": "PERSON_abcdef", "reason": "x" * 12})
        assert r.status_code == 403
        assert a.c.crypto.audit.store.all()[-1].event == "reidentify_denied"


def test_admin_passes_every_admin_gate(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("boss@x.io", "admin")
        a.login("boss@x.io")
        for method, path in api_routes(a):
            if path.startswith(ADMIN_ONLY_PREFIX):
                r = call(a, method, path)
                assert r.status_code not in (401, 403), (method, path, r.status_code)


def test_service_checks_role_again() -> None:
    from app.storage.rows import UserRow

    user = UserRow(1, "u@x.io", "$2b$" + "a" * 56, "user", True, "2026-11-19T10:00:00.000Z")
    svc = AdminService(SimpleNamespace(db=None), user)  # type: ignore[arg-type]  # no storage
    for fn in (svc.get_rules, svc.reset_beliefs, svc.verify, svc.save_anchor):
        with pytest.raises(AppError) as e:
            fn()
        assert e.value.code == "forbidden"
    with pytest.raises(AppError):
        svc.audit_page(None, 10)
    with pytest.raises(AppError):
        svc.put_rules([])


def test_login_again_ends_the_old_session(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        http = a.login("a@x.io")
        first = http.cookies.get("pg_session")
        r = a.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW})
        assert r.status_code == 204
        second = http.cookies.get("pg_session")
        assert first and second and first != second  # new id on every login
        http.cookies.clear()
        http.cookies.set("pg_session", first)
        assert http.get("/api/v1/auth/me").status_code == 401
        http.cookies.clear()
        http.cookies.set("pg_session", second)
        assert http.get("/api/v1/auth/me").status_code == 200


def test_dead_cookie_is_cleared(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.http.cookies.set("pg_session", "not-a-real-session")
        r = a.http.get("/api/v1/auth/me")
        assert r.status_code == 401
        assert "pg_session=;" in r.headers["set-cookie"] and "Max-Age=0" in r.headers["set-cookie"]
        a.http.cookies.clear()
        assert "set-cookie" not in a.http.get("/api/v1/auth/me").headers  # no cookie, no header


def test_expired_session_row_is_deleted(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with api(tmp_path) as a:
        a.user("a@x.io")
        http = a.login("a@x.io")
        later = clock.now() + clock.timedelta(days=8)
        monkeypatch.setattr(clock, "now", lambda: later)
        assert http.get("/api/v1/auth/me").json()["error"]["code"] == "session_expired"
        assert a.c.auth.sessions.delete_expired("9999-01-01T00:00:00.000Z") == 0


def test_session_never_outlives_max_age(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Active every few hours for 7+ days: still ends at 7 days total."""
    with api(tmp_path) as a:
        a.user("a@x.io")
        http = a.login("a@x.io")
        start = clock.now()
        for h in range(4, 7 * 24, 4):
            t = start + clock.timedelta(hours=h)
            monkeypatch.setattr(clock, "now", lambda t=t: t)
            assert http.get("/api/v1/auth/me").status_code == 200, h
        t = start + clock.timedelta(days=7, hours=1)
        monkeypatch.setattr(clock, "now", lambda: t)
        assert http.get("/api/v1/auth/me").status_code == 401


def test_session_token_stored_only_as_hash(tmp_path: Path) -> None:
    from sqlalchemy import text

    with api(tmp_path) as a:
        a.user("a@x.io")
        token = a.login("a@x.io").cookies.get("pg_session") or ""
        with a.c.db.transaction() as conn:
            rows = conn.execute(text("SELECT id_hash FROM sessions")).all()
            pw = conn.execute(text("SELECT password_hash FROM users")).scalar_one()
        assert len(rows) == 1 and token.encode() not in bytes(rows[0][0])
        assert len(bytes(rows[0][0])) == 32 and pw.startswith("$2b$") and PW not in pw


def test_rate_limiter_memory_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.ratelimit as rl

    monkeypatch.setattr(rl, "MAX_KEYS", 100)
    now = [0.0]
    lim = RateLimiter(clock=lambda: now[0])
    for i in range(1000):
        lim.hit(f"login:{i}@x.io", 5, 300)
        now[0] += 1
    assert len(lim._hits) <= 100
    # failures are still counted after the cap kicked in
    for _ in range(5):
        lim.add("login:victim")
    assert lim.retry_after("login:victim", 5, 300) > 0
