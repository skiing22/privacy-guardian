"""Auth, sessions, origin check, headers, rate limits, role checks (API 2, 3, 7)."""

from pathlib import Path

from app.services import auth as auth_mod
from app.services import clock
from tests.api_helpers import ORIGIN, PW, api


def test_login_me_logout(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("Ana@x.io")
        http = a.login("ana@X.io")  # case-insensitive email
        cookie = http.cookies.get("pg_session")
        assert cookie
        r = http.get("/api/v1/auth/me")
        assert r.json()["email"] == "Ana@x.io" and r.json()["role"] == "user"
        for h in ("x-request-id", "x-content-type-options", "content-security-policy"):
            assert h in r.headers
        assert r.headers["cache-control"] == "no-store"
        assert a.post("/api/v1/auth/logout").status_code == 204
        http.cookies.set("pg_session", cookie)  # replay the old cookie
        assert http.get("/api/v1/auth/me").json()["error"]["code"] == "auth_required"


def test_cookie_flags(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        r = a.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW})
        sc = r.headers["set-cookie"].lower()
        assert "httponly" in sc and "samesite=strict" in sc and "path=/" in sc


def test_wrong_password_and_unknown_email_look_the_same(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        r1 = a.post("/api/v1/auth/login", json={"email": "a@x.io", "password": "wrongpass1"})
        r2 = a.post("/api/v1/auth/login", json={"email": "no@x.io", "password": "wrongpass1"})
        assert r1.status_code == r2.status_code == 401
        assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


def test_lockout_after_five_failures(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        bad = {"email": "a@x.io", "password": "wrongpass1"}
        for _ in range(5):
            assert a.post("/api/v1/auth/login", json=bad).status_code == 401
        r = a.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW})
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_disabled_user_cannot_log_in_and_sessions_end(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        http = a.login("a@x.io")
        a.c.auth.disable_user("a@x.io")
        assert http.get("/api/v1/auth/me").status_code == 401
        r = a.post("/api/v1/auth/login", json={"email": "a@x.io", "password": PW})
        assert r.json()["error"]["code"] == "auth_failed"


def test_session_expiry(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with api(tmp_path) as a:
        a.user("a@x.io")
        http = a.login("a@x.io")
        later = clock.now() + clock.timedelta(hours=9)  # idle limit is 8 h
        monkeypatch.setattr(clock, "now", lambda: later)
        assert http.get("/api/v1/auth/me").json()["error"]["code"] == "session_expired"


def test_origin_check(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("a@x.io")
        body = {"email": "a@x.io", "password": PW}
        assert a.http.post("/api/v1/auth/login", json=body).json()["error"]["code"] == "bad_origin"
        r = a.http.post("/api/v1/auth/login", json=body, headers={"Origin": "https://evil.io"})
        assert r.status_code == 400
        r = a.http.post("/api/v1/auth/login", json=body, headers={"Origin": ORIGIN})
        assert r.status_code == 204


def test_validation_errors_never_echo_input(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        r = a.post(
            "/api/v1/auth/login", json={"email": "a@x.io", "password": "x", "extra": "SECRET-123"}
        )
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
        assert "SECRET-123" not in r.text


def test_routes_need_login_and_admin_needs_role(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        for path in ("/api/v1/auth/me", "/api/v1/scans", "/api/v1/admin/rules"):
            assert a.http.get(path).status_code == 401
        a.user("u@x.io")
        http = a.login("u@x.io")
        for path in ("/api/v1/admin/rules", "/api/v1/admin/audit"):
            assert http.get(path).json()["error"]["code"] == "forbidden"
        r = a.post("/api/v1/admin/audit/anchor")
        assert r.status_code == 403


def test_passwords_hashed_with_prehash(tmp_path: Path) -> None:
    auth_mod.BCRYPT_ROUNDS = 4
    long_a, long_b = "a" * 100 + "1", "a" * 100 + "2"  # differ after byte 72
    h = auth_mod.hash_password(long_a)
    assert len(h) == 60 and auth_mod.check_password(long_a, h)
    assert not auth_mod.check_password(long_b, h)
