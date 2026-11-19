"""Background threads in the single process (ADR-0022 D17):

- model loader: loads the NER model once, then marks the app ready (/health 200)
- scan worker: one scan at a time from the in-memory queue; waits for the model
- retention: at startup, then every 24 hours
"""

import hashlib
import logging
import threading
from pathlib import Path

from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import Span
from app.graph.build import Detector
from app.parsers.chunking import ChunkedDetector
from app.services import clock
from app.services.container import Container
from app.services.retention import run_retention
from app.services.scan_runner import ScanRunner
from app.storage.worker_repo import WorkerRepo

log = logging.getLogger("app.worker")
RETENTION_EVERY_S = 24 * 3600.0


def model_version(path: str) -> str | None:
    """Short fingerprint of the model config, stored on each scan and in reports."""
    p = Path(path)
    for name in ("VERSION", "config.json"):
        f = p / name
        if f.is_file():
            data = f.read_bytes()
            return data.decode().strip()[:40] if name == "VERSION" else hashlib.sha256(
                data).hexdigest()[:12]  # fmt: skip
    return None


class _NoNer:
    """Dev only, when no model is on disk: rules + context still run, names are missed."""

    def detect(self, text: str) -> list[Span]:
        return []


def load_detectors(c: Container) -> dict[str, Detector]:
    from app.detectors.ner import NerDetector

    s = c.settings
    if s.env == "dev" and not Path(s.ner_model_path).exists():
        log.warning("no NER model found: dev mode runs rules and context only",
                    extra={"event": "model_missing"})  # fmt: skip
        return {"rules": RuleDetector(), "ner": _NoNer(), "context": ContextDetector()}
    ner = NerDetector(s.ner_model_path, threshold=s.ner_threshold)
    ner.detect("Warm up with Rahul in Kochi.")  # load weights now, not on the first scan
    return {"rules": RuleDetector(), "ner": ChunkedDetector(ner), "context": ContextDetector()}


def load_model(c: Container) -> None:
    try:
        if c.detectors is None:
            c.detectors = load_detectors(c)
            c.model_version = model_version(c.settings.ner_model_path)
        c.model_ready.set()
        log.info("model ready", extra={"event": "model_ready"})
    except Exception as e:  # stays not ready: /health keeps answering 503
        log.error("model failed to load", extra={"error_code": type(e).__name__})


def worker_loop(c: Container, stop: threading.Event) -> None:
    runner = ScanRunner(c)
    while not stop.is_set():
        if not c.model_ready.wait(timeout=1.0):
            continue
        job = c.jobs.get()
        if job is None:
            return
        try:
            runner.run(job)
        except Exception as e:  # pragma: no cover - runner catches its own errors
            log.error(
                "worker error", extra={"scan_id": job.scan_id, "error_code": type(e).__name__}
            )


def retention_loop(c: Container, stop: threading.Event) -> None:
    while True:
        try:
            run_retention(c)
        except Exception as e:
            log.error("retention failed", extra={"error_code": type(e).__name__})
        if stop.wait(RETENTION_EVERY_S):
            return


class Runtime:
    def __init__(self, c: Container) -> None:
        self.c = c
        self.stop = threading.Event()
        self.threads: list[threading.Thread] = []

    def start(self, retention: bool = True) -> None:
        # Scans left open by a crash or restart go back in the queue (API 6).
        repo = WorkerRepo(self.c.db)
        for sid in repo.open_ids():
            repo.set_state(sid, "queued", clock.iso(clock.now()))
            self.c.enqueue(sid)
        targets = [("model-loader", lambda: load_model(self.c)),
                   ("scan-worker", lambda: worker_loop(self.c, self.stop))]  # fmt: skip
        if retention:
            targets.append(("retention", lambda: retention_loop(self.c, self.stop)))
        for name, fn in targets:
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()
            self.threads.append(t)

    def shutdown(self, timeout: float = 5.0) -> None:
        self.stop.set()
        self.c.jobs.put(None)
        for t in self.threads:
            t.join(timeout)
