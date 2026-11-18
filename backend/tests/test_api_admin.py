"""Admin endpoints (API 4.13-4.19), J4 audit verify, retention, admin bootstrap."""

from pathlib import Path

from sqlalchemy import text

from app.services import clock
from app.services.retention import run_retention
from tests.api_helpers import ORIGIN, Api, api

TEXT = "Patient: Rahul Sharma, phone 98470 12345."


def admin(a: Api) -> None:
    a.user("boss@x.io", "admin")
    a.login("boss@x.io")


def scan_done(a: Api) -> dict:  # type: ignore[type-arg]
    sid = a.post("/api/v1/scans", data={"text": TEXT}).json()["id"]
    a.drain()
    return a.http.get(f"/api/v1/scans/{sid}/result").json()  # type: ignore[no-any-return]


def test_rules_roundtrip_and_used_by_next_scan(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        admin(a)
        rules = a.http.get("/api/v1/admin/rules").json()["rules"]
        assert len(rules) == 15 and all(r["action"] is None for r in rules)
        bad = a.http.put(
            "/api/v1/admin/rules",
            headers={"Origin": ORIGIN},
            json={"rules": [{"pii_type": "AGE", "action": "mask"}]},
        )
        assert bad.json()["error"]["code"] == "action_not_allowed"
        ok = a.http.put(
            "/api/v1/admin/rules",
            headers={"Origin": ORIGIN},
            json={"rules": [{"pii_type": "PERSON", "action": "redact"}]},
        )
        person = next(r for r in ok.json()["rules"] if r["pii_type"] == "PERSON")
        assert person["action"] == "redact" and person["updated_at"]
        res = scan_done(a)
        item = next(i for i in res["items"] if i["pii_type"] == "PERSON")
        assert item["action"] == "redact" and item["reason"] == "override"


def test_reveal_admin_and_non_admin(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        a.user("u@x.io")
        admin(a)
        token = next(i["token"] for i in scan_done(a)["items"] if i["pii_type"] == "PERSON")
        short = a.post("/api/v1/admin/reveal", json={"token": token, "reason": "short"})
        assert short.json()["error"]["code"] == "reason_too_short"
        r = a.post("/api/v1/admin/reveal", json={"token": token, "reason": "court order 2026/77"})
        assert r.status_code == 200 and r.json()["value"] == "Rahul Sharma"
        assert r.json()["logged_as"] is not None
        unknown = a.post(
            "/api/v1/admin/reveal", json={"token": "PERSON_000000", "reason": "court order 2026/77"}
        )
        assert unknown.json()["error"]["code"] == "unknown_token"
        a.login("u@x.io")
        denied = a.post("/api/v1/admin/reveal", json={"token": token, "reason": "court order 2026"})
        assert denied.status_code == 403
        events = [x.event for x in a.c.crypto.audit.store.all()]
        assert "reidentify" in events and events[-1] == "reidentify_denied"
        assert "Rahul" not in str([x.payload for x in a.c.crypto.audit.store.all()])


def test_audit_page_verify_anchor_and_tamper(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        admin(a)
        scan_done(a)
        v = a.post("/api/v1/admin/audit/verify").json()
        assert v["ok"] and v["anchor"] is None
        anc = a.post("/api/v1/admin/audit/anchor").json()
        assert len(anc["mac_prefix"]) == 16
        page = a.http.get("/api/v1/admin/audit?limit=1").json()
        assert page["items"][0]["event"] == "anchor_saved"
        assert page["items"][0]["actor"]["email"] == "boss@x.io"
        assert page["next_before_seq"] is not None
        # tamper: drop the trigger with raw SQL and change a record
        with a.c.db.transaction() as conn:
            conn.execute(text("DROP TRIGGER audit_no_update"))
            conn.execute(text("UPDATE audit_log SET payload = '{}' WHERE seq = 0"))
        v = a.post("/api/v1/admin/audit/verify").json()
        assert not v["ok"] and v["first_bad_seq"] == 0 and v["anchor"]["seq"] == anc["seq"]


def test_beliefs_reset(tmp_path: Path) -> None:
    with api(tmp_path) as a:
        admin(a)
        assert a.post("/api/v1/admin/beliefs/reset", json={"confirm": False}).status_code == 422
        assert a.post("/api/v1/admin/beliefs/reset", json={"confirm": True}).status_code == 204
        assert a.c.crypto.audit.store.all()[-1].event == "beliefs_reset"


def test_retention_deletes_expired(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with api(tmp_path) as a:
        admin(a)
        res = scan_done(a)
        later = clock.now() + clock.timedelta(days=9)
        monkeypatch.setattr(clock, "now", lambda: later)
        counts = run_retention(a.c)
        assert counts["scans"] == 1 and counts["vault"] >= 1
        assert res["id"] not in a.c.files.scan_ids()
        assert a.c.crypto.audit.store.all()[-1].event == "retention"


def test_admin_bootstrap_from_env(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    s = Settings(
        data_dir=tmp_path,
        static_dir=Path("/x"),
        admin_email="root@x.io",
        admin_password="bootstrap-pass-1",
    )  # type: ignore[arg-type]
    import app.services.auth as auth

    auth.BCRYPT_ROUNDS = 4
    for _ in range(2):  # second start: users exist, nothing new
        with TestClient(create_app(s, start_threads=False)) as c:
            users = c.app.state.container.auth.users  # type: ignore[attr-defined]
            assert users.count() == 1
