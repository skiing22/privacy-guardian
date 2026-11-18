"""Shared harness: real app + SQLite in a temp dir, fake NER, worker driven by the test."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType
from app.main import create_app
from app.services.container import Container
from app.services.scan_runner import ScanRunner
from tests.test_graph import FakeNer

ORIGIN = "http://localhost:8000"
HITS = [("Rahul Sharma", PiiType.PERSON, 0.95), ("Priya", PiiType.PERSON, 0.6)]
PW = "correct horse 1"


class Api:
    def __init__(self, client: TestClient) -> None:
        self.http = client
        self.c: Container = client.app.state.container  # type: ignore[attr-defined]

    def user(self, email: str, role: str = "user") -> int:
        return self.c.auth.create_user(email, PW, role)

    def login(self, email: str) -> TestClient:
        self.http.cookies.clear()
        r = self.http.post(
            "/api/v1/auth/login", json={"email": email, "password": PW}, headers={"Origin": ORIGIN}
        )
        assert r.status_code == 204, r.text
        return self.http

    def post(self, url: str, **kw: object):  # type: ignore[no-untyped-def]
        return self.http.post(url, headers={"Origin": ORIGIN}, **kw)  # type: ignore[arg-type]

    def drain(self) -> None:
        """Run queued jobs on this thread (the real worker is a background thread)."""
        runner = ScanRunner(self.c)
        while not self.c.jobs.empty():
            job = self.c.jobs.get_nowait()
            if job is not None:
                runner.run(job)


@contextmanager
def api(tmp: Path, hits: list[tuple[str, PiiType, float]] | None = None) -> Iterator[Api]:
    import app.services.auth as auth

    auth.BCRYPT_ROUNDS = 4
    s = Settings(data_dir=tmp, static_dir=Path("/nonexistent"))
    dets = {
        "rules": RuleDetector(),
        "ner": FakeNer(HITS if hits is None else hits),
        "context": ContextDetector(),
    }
    with TestClient(create_app(s, detectors=dets, start_threads=False)) as client:  # type: ignore[arg-type]
        a = Api(client)
        a.c.model_ready.set()
        yield a
