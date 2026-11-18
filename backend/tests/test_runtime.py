"""Real background threads: model loader, worker, retention; restart recovery (J5)."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType
from app.main import create_app
from app.runtime.worker import model_version
from app.storage.worker_repo import WorkerRepo
from tests.api_helpers import ORIGIN, PW
from tests.test_graph import FakeNer


def wait_status(http: TestClient, sid: str, want: str, timeout: float = 10.0) -> dict:  # type: ignore[type-arg]
    end = time.time() + timeout
    while time.time() < end:
        st = http.get(f"/api/v1/scans/{sid}").json()
        if st["status"] == want:
            return st  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError(f"scan stayed {st['status']}")


def test_threads_run_scans_and_recover_after_restart(tmp_path: Path) -> None:
    import app.services.auth as auth

    auth.BCRYPT_ROUNDS = 4
    s = Settings(data_dir=tmp_path, static_dir=Path("/x"))
    dets = {
        "rules": RuleDetector(),
        "ner": FakeNer([("Rahul Sharma", PiiType.PERSON, 0.95)]),
        "context": ContextDetector(),
    }
    with TestClient(create_app(s, detectors=dets)) as http:  # type: ignore[arg-type]
        c = http.app.state.container  # type: ignore[attr-defined]
        c.auth.create_user("a@x.io", PW, "user")
        http.post(
            "/api/v1/auth/login",
            json={"email": "a@x.io", "password": PW},
            headers={"Origin": ORIGIN},
        )
        assert http.get("/health").status_code == 200
        sid = http.post(
            "/api/v1/scans", data={"text": "Rahul Sharma called."}, headers={"Origin": ORIGIN}
        ).json()["id"]
        wait_status(http, sid, "done")
        # simulate a crash mid-scan: a second scan left "running" in the database
        sid2 = http.post(
            "/api/v1/scans", data={"text": "Rahul Sharma again."}, headers={"Origin": ORIGIN}
        ).json()["id"]
        wait_status(http, sid2, "done")
        WorkerRepo(c.db).set_state(sid2, "running", "2026-11-19T10:00:00.000Z", step=2)
        cookie = http.cookies.get("pg_session")

    with TestClient(create_app(s, detectors=dets)) as http:  # type: ignore[arg-type]
        http.cookies.set("pg_session", cookie or "")
        assert wait_status(http, sid2, "done")["step"] == 5


def test_model_version(tmp_path: Path) -> None:
    assert model_version(str(tmp_path)) is None
    (tmp_path / "config.json").write_text("{}")
    assert len(model_version(str(tmp_path)) or "") == 12
    (tmp_path / "VERSION").write_text("v2-a41c07\n")
    assert model_version(str(tmp_path)) == "v2-a41c07"
