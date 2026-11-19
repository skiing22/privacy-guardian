"""Runs one scan job on the worker thread (ARCHITECTURE 4.3, API 6).

queued -> running (step 1 parse) -> graph nodes (steps 2-5, round 1-3)
       -> needs_review (graph paused; answers come back as a new job)
       -> done (decisions + cleaned file + scan row + audit: one transaction)
       -> failed (error_code + step; checkpoint kept so retry can resume)
"""

import concurrent.futures as cf
import logging
from collections import Counter
from typing import Any

from langgraph.types import Command

from app.graph.build import build_graph, result_of
from app.output.segments import Item, OutputError, rebuild
from app.output.writers import CONTENT_TYPES, write
from app.parsers.base import ParsedDoc, ParseError
from app.parsers.files import parse_bytes
from app.policy.utility import PolicyConfig
from app.services import clock
from app.services.container import Container, Job
from app.storage.files import FileIntegrityError
from app.storage.repos import RuleRepo
from app.storage.rows import DecisionRow, ScanRow
from app.storage.worker_repo import WorkerRepo, file_meta

log = logging.getLogger("app.worker")
PARSE_TIMEOUT_S = 60.0
_NODE_STEP = {"fuse": 3, "review": 4, "policy": 4, "verify": 5, "finalize": 5}
_parse_pool = cf.ThreadPoolExecutor(max_workers=1, thread_name_prefix="parse")


class ScanFailedError(Exception):
    def __init__(self, code: str, step: int) -> None:
        super().__init__(code)
        self.code, self.step = code, step


def cfg(scan_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": scan_id}}


def parse_original(c: Container, row: ScanRow) -> tuple[bytes, ParsedDoc]:
    meta = file_meta(c.db, row.id, "original")
    if meta is None:
        raise ScanFailedError("file_unreadable", 1)
    try:
        data = c.files.read(row.id, "original", meta.stored)
    except FileIntegrityError as e:
        raise ScanFailedError("file_unreadable", 1) from e
    name = f"x.{row.format}"
    fut = _parse_pool.submit(parse_bytes, data, name)
    try:
        doc = fut.result(timeout=PARSE_TIMEOUT_S)
    except cf.TimeoutError as e:
        raise ScanFailedError("file_unreadable", 1) from e
    except ParseError as e:
        code = "pdf_no_text" if "no text layer" in str(e) else "file_unreadable"
        raise ScanFailedError(code, 1) from e
    return data, doc


class ScanRunner:
    def __init__(self, c: Container) -> None:
        self.c = c
        self.repo = WorkerRepo(c.db)

    def _now(self) -> str:
        return clock.iso(clock.now())

    def run(self, job: Job) -> None:
        row = self.repo.get(job.scan_id)
        if row is None or row.status != "queued":
            return  # deleted, or already handled
        step = 1
        self.repo.set_state(row.id, "running", self._now(), step=1)
        log.info("scan started", extra={"scan_id": row.id, "event": "scan_started"})
        try:
            original, doc = parse_original(self.c, row)
            step = 2
            if not doc.text.strip():  # e.g. a CSV with only a header: nothing to find
                self._finish_empty(row, original)
                return
            self._run_graph(row, job, original, doc)
        except ScanFailedError as e:
            self._fail(row.id, e.code, e.step)
        except OutputError:
            self._fail(row.id, "internal", 5)
        except Exception as e:  # never let one scan stop the worker
            log.error("scan failed", extra={"scan_id": row.id, "error_code": type(e).__name__})
            self._fail(row.id, "internal", step)

    def _fail(self, scan_id: str, code: str, step: int) -> None:
        self.repo.set_state(scan_id, "running", self._now(), step=step)
        self.repo.fail(scan_id, code, self._now())
        log.info("scan failed", extra={"scan_id": scan_id, "error_code": code, "step": step})

    def _graph(self, row: ScanRow) -> Any:
        rules = RuleRepo(self.c.db).all()
        policy = PolicyConfig(overrides={t: a for t, (a, _) in rules.items()})
        deps = self.c.graph_deps(
            policy=policy,
            crypto=self.c.crypto_for(f"user:{row.owner_id}"),
            audit_scan_completed=False,
            fuse_threshold=self.c.settings.ner_threshold,
        )
        return build_graph(deps, checkpointer=self.c.saver)

    def _run_graph(self, row: ScanRow, job: Job, original: bytes, doc: ParsedDoc) -> None:
        graph = self._graph(row)
        snap = graph.get_state(cfg(row.id))
        inp: Any
        if job.answers is not None:
            inp = Command(resume=job.answers)
        elif snap.values and snap.interrupts:
            # restart while paused: the answers were lost with the process, ask again
            self.repo.set_state(row.id, "needs_review", self._now(), step=3)
            return
        elif snap.values and snap.next:
            inp = None  # resume after a crash or a retry: continue from the checkpoint
        elif snap.values:
            inp = None
        else:
            inp = {
                "scan_id": row.id, "org": "default", "original": doc.text, "text": doc.text,
                "round": 0, "allowed_values": [],
            }  # fmt: skip

        rnd = int(snap.values.get("round", 0)) + 1 if snap.values else 1
        if inp is not None or snap.next:
            for update in graph.stream(inp, cfg(row.id), stream_mode="updates"):
                for node in update:
                    if node.startswith("__"):
                        continue
                    if node == "next_round":
                        rnd += 1
                    step = 2 if node.startswith("detect_") else _NODE_STEP.get(node, 2)
                    self.repo.set_state(row.id, "running", self._now(), step=step, round_=rnd)
            snap = graph.get_state(cfg(row.id))
        if snap.interrupts:
            self.repo.set_state(row.id, "needs_review", self._now(), step=3)
            log.info("scan needs review", extra={"scan_id": row.id, "event": "needs_review"})
            return
        self._finish(row, original, doc, dict(snap.values))

    def _finish_empty(self, row: ScanRow, original: bytes) -> None:
        """PRD 12: "No personal data found." The cleaned file is the original."""
        stored = self.c.files.write(row.id, "cleaned", original)
        now = self._now()
        crypto = self.c.crypto_for(f"user:{row.owner_id}")
        fmt = "txt" if row.format == "pdf" else row.format
        with self.c.db.transaction():
            self.repo.replace_decisions(row.id, [])
            self.repo.put_file(row.id, "cleaned", CONTENT_TYPES.get(fmt, CONTENT_TYPES["txt"]),
                               stored.size_bytes, stored.key_id, stored.nonce, now)  # fmt: skip
            self.repo.finish(row.id, "LOW", 0.0, [], 0, 1, self.c.model_version, now)
            crypto.audit.append(crypto.actor, "scan_completed", {
                "scan": row.id, "rounds": 1, "risk": "LOW", "unresolved_leaks": 0, "counts": {},
            })  # fmt: skip
        self.c.saver.delete_thread(row.id)
        log.info("scan done", extra={"scan_id": row.id, "event": "scan_done", "count": 0})

    def _finish(
        self, row: ScanRow, original: bytes, doc: ParsedDoc, values: dict[str, Any]
    ) -> None:
        res = result_of(values)
        items: list[Item] = []
        rows: list[DecisionRow] = []
        counts: Counter[str] = Counter()
        for rec in res.history:
            for k, (sp, d) in enumerate(zip(rec.spans, rec.decisions, strict=True)):
                tok = rec.tokens[k] if k < len(rec.tokens) else None
                idx = len(items)
                items.append(Item(idx, rec.round + 1, sp.start, sp.end, sp.pii_type, d.action, tok))
                rows.append(DecisionRow(
                    row.id, idx, rec.round + 1, sp.start, sp.end, sp.pii_type.value,
                    round(sp.score, 4), sp.source, d.action.value, d.reason, tok,
                ))  # fmt: skip
                counts[f"{sp.pii_type.value}:{d.action.value}"] += 1
        rebuilt = rebuild(doc, items)
        if rebuilt.text != res.output:
            raise OutputError("rebuilt output does not match the graph output")
        cleaned = write(row.format, original, doc, rebuilt)
        stored = self.c.files.write(row.id, "cleaned", cleaned.data)
        now = self._now()
        crypto = self.c.crypto_for(f"user:{row.owner_id}")
        with self.c.db.transaction():
            self.repo.replace_decisions(row.id, rows)
            self.repo.put_file(row.id, "cleaned", cleaned.content_type, stored.size_bytes,
                               stored.key_id, stored.nonce, now)  # fmt: skip
            self.repo.finish(
                row.id, res.risk.level.value, res.risk.est_matches, list(res.risk.clues),
                len(res.unresolved_leaks), res.rounds, self.c.model_version, now,
            )  # fmt: skip
            crypto.audit.append(crypto.actor, "scan_completed", {
                "scan": row.id, "rounds": res.rounds, "risk": res.risk.level.value,
                "unresolved_leaks": len(res.unresolved_leaks), "counts": dict(counts),
            })  # fmt: skip
        self.c.saver.delete_thread(row.id)
        log.info("scan done", extra={"scan_id": row.id, "event": "scan_done", "count": len(rows)})
