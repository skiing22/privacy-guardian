"""Everything a request or the worker needs, built once at startup (ARCHITECTURE 3).

Owns: the database, the encrypted file store, the checkpointer, the crypto services
(one AuditLog, so its lock covers every writer), the learner, rate limits and the queue.
"""

import json
import os
import queue
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import Settings
from app.crypto.audit import Anchor
from app.crypto.keys import KeyRing, Purpose
from app.crypto.services import CryptoServices
from app.detectors.types import Span
from app.graph.build import Detector, GraphDeps, build_graph
from app.graph.checkpoints import open_checkpointer
from app.policy.beliefs import BeliefLearner
from app.services import clock
from app.services.auth import AuthService
from app.services.ratelimit import RateLimiter
from app.storage.db import Database
from app.storage.files import EncryptedFileStore
from app.storage.stores import SqlAuditStore, SqlBeliefStore, SqlTokenRegistry, SqlVaultStore

DETECTOR_NAMES = ("rules", "ner", "context")


@dataclass(frozen=True)
class Job:
    scan_id: str
    answers: list[dict[str, Any]] | None = None


class _Unused:
    def detect(self, text: str) -> list[Span]:  # pragma: no cover - never run
        raise RuntimeError("reader graph never runs detectors")


@dataclass
class Container:
    settings: Settings
    db: Database
    files: EncryptedFileStore
    saver: SqliteSaver
    crypto: CryptoServices
    learner: BeliefLearner
    limiter: RateLimiter
    auth: AuthService
    jobs: "queue.Queue[Job | None]" = field(default_factory=queue.Queue)
    detectors: dict[str, Detector] | None = None
    model_ready: threading.Event = field(default_factory=threading.Event)
    model_version: str | None = None
    reader: Any = None  # graph used only to read checkpoints (status, review items)

    @classmethod
    def build(cls, settings: Settings, ring: KeyRing) -> "Container":
        data = settings.data_dir
        db = Database.at(data)
        crypto = CryptoServices.build(
            ring, SqlAuditStore(db), SqlVaultStore(db), SqlTokenRegistry(db), actor="system"
        )
        limiter = RateLimiter()
        c = cls(
            settings=settings,
            db=db,
            files=EncryptedFileStore(data / "files", ring[Purpose.STORAGE]),
            saver=open_checkpointer(data / "checkpoints.db", ring[Purpose.STORAGE]),
            crypto=crypto,
            learner=BeliefLearner(SqlBeliefStore(db)),
            limiter=limiter,
            auth=AuthService(
                db, crypto.audit, limiter, settings.session_idle_hours, settings.session_max_days
            ),
        )
        stub: dict[str, Detector] = {n: _Unused() for n in DETECTOR_NAMES}
        c.reader = build_graph(GraphDeps(detectors=stub), checkpointer=c.saver)
        return c

    def crypto_for(self, actor: str) -> CryptoServices:
        return replace(self.crypto, actor=actor)

    def graph_deps(self, **kw: Any) -> GraphDeps:
        assert self.detectors is not None, "model not ready"
        return GraphDeps(detectors=self.detectors, learner=self.learner, **kw)

    def enqueue(self, scan_id: str, answers: list[dict[str, Any]] | None = None) -> None:
        self.jobs.put(Job(scan_id, answers))

    # ---- audit anchor: a separate file, outside the database it protects (D10) ----

    @property
    def anchor_path(self) -> Path:
        return self.settings.data_dir / "audit.anchor.json"

    def load_anchor(self) -> tuple[Anchor, str] | None:
        try:
            d = json.loads(self.anchor_path.read_text())
            return Anchor(int(d["seq"]), str(d["mac"])), str(d["saved_at"])
        except FileNotFoundError:
            return None

    def save_anchor(self, a: Anchor) -> str:
        saved_at = clock.iso(clock.now())
        tmp = self.anchor_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"seq": a.seq, "mac": a.mac, "saved_at": saved_at}))
        os.replace(tmp, self.anchor_path)
        return saved_at

    def close(self) -> None:
        self.jobs.put(None)
        self.saver.conn.close()
        self.db.engine.dispose()
