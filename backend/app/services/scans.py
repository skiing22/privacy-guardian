"""Scan use cases for one logged-in user (API 4.5 to 4.12). Every read goes through the
owner-scoped ScanRepo, so another user's scan is simply "not found" (404, never 403)."""

import base64
import binascii
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.detectors.types import PiiType
from app.graph.build import MAX_ROUNDS_DEFAULT
from app.output.labels import (
    ACTION_LABEL,
    FAMILY,
    LATER_ROUND_TEXT,
    REASON_TEXT,
    STEP_LABEL,
)
from app.output.segments import Item, rebuild
from app.parsers.validate import (
    MAX_TEXT_CHARS,
    PASTED_NAME,
    UploadRejectedError,
    check_text,
    check_upload,
    clean_filename,
)
from app.policy.actions import Action
from app.services import clock
from app.services.container import Container
from app.services.errors import MESSAGES, AppError
from app.services.scan_runner import ScanFailedError, cfg, parse_original
from app.storage.repos import ScanRepo
from app.storage.rows import DecisionRow, ScanRow, UserRow
from app.storage.worker_repo import WorkerRepo, running_count

SCANS_PER_HOUR = (20, 3600.0)
MAX_OPEN = 3
CONTEXT_CHARS = 60
OPEN = ("queued", "running", "needs_review")


def _risk(s: ScanRow) -> dict[str, Any] | None:
    if s.status != "done":
        return None
    return {"level": s.risk_level, "est_matches": s.est_matches, "clues": s.risk_clues or [],
            "unresolved_leaks": s.unresolved_leaks}  # fmt: skip


def encode_cursor(s: ScanRow) -> str:
    raw = json.dumps([s.created_at, s.id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        pad = "=" * (-len(cursor) % 4)
        created, sid = json.loads(base64.urlsafe_b64decode(cursor + pad))
        uuid.UUID(sid)
        clock.parse(created)
        return str(created), str(sid)
    except (ValueError, TypeError, binascii.Error) as e:
        raise AppError("invalid_request", "Invalid cursor.", "cursor") from e


@dataclass(frozen=True)
class Download:
    data: bytes
    content_type: str
    filename: str


class ScanService:
    def __init__(self, c: Container, user: UserRow) -> None:
        self.c, self.user = c, user
        self.repo = ScanRepo(c.db, user.id)

    def _get(self, scan_id: str) -> ScanRow:
        try:
            uuid.UUID(scan_id)
        except ValueError as e:
            raise AppError("not_found") from e
        s = self.repo.get(scan_id)
        if s is None:
            raise AppError("not_found")
        return s

    # ---- 4.5 create ----

    def create(self, filename: str | None, data: bytes | None, text: str | None) -> ScanRow:
        if (data is None) == (text is None):
            raise AppError("empty_input")
        try:
            if data is not None:
                name = clean_filename(filename or "file")
                fmt = check_upload(name, data)
            else:
                name, fmt, data = PASTED_NAME, "txt", check_text(text or "")
        except UploadRejectedError as e:
            if e.code == "text_too_long":
                msg = f"Text is too long (max {MAX_TEXT_CHARS:,} characters)."
                raise AppError("invalid_request", msg, "text") from e
            raise AppError(e.code, mb=self.c.settings.max_upload_mb) from e
        if self.repo.open_count() >= MAX_OPEN:
            raise AppError("rate_limited", headers={"Retry-After": "30"}, n=30)
        self.c.limiter.hit(f"scans:{self.user.id}", *SCANS_PER_HOUR)

        scan_id = str(uuid.uuid4())
        now = clock.now()
        exp = now + clock.timedelta(days=self.c.settings.retention_days)
        try:
            stored = self.c.files.write(scan_id, "original", data)
        except OSError as e:
            raise AppError("storage_unavailable") from e
        try:
            with self.c.db.transaction():
                self.repo.create(scan_id, name, fmt, clock.iso(now), clock.iso(exp))
                WorkerRepo(self.c.db).put_file(scan_id, "original", "application/octet-stream",
                                               stored.size_bytes, stored.key_id, stored.nonce,
                                               clock.iso(now))  # fmt: skip
        except Exception:
            self.c.files.delete_scan(scan_id)
            raise
        self.c.enqueue(scan_id)
        s = self.repo.get(scan_id)
        assert s is not None
        return s

    # ---- 4.6 list ----

    def page(self, status: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
        before = decode_cursor(cursor) if cursor else None
        rows = self.repo.page(status, before, limit + 1)
        more = len(rows) > limit
        rows = rows[:limit]
        return {
            "items": [
                {
                    "id": s.id,
                    "filename": s.filename,
                    "format": s.format,
                    "status": s.status,
                    "risk_level": s.risk_level,
                    "created_at": s.created_at,
                    "expires_at": s.expires_at,
                }  # fmt: skip
                for s in rows
            ],
            "next_cursor": encode_cursor(rows[-1]) if more and rows else None,
        }

    # ---- 4.7 status ----

    def _review(self, s: ScanRow) -> dict[str, Any] | None:
        if s.status != "needs_review":
            return None
        snap = self.c.reader.get_state(cfg(s.id))
        if not snap.interrupts:
            return {"items": []}
        text, spans = snap.values["text"], snap.values["spans"]
        out = []
        for it in snap.interrupts[0].value["items"]:
            sp = spans[int(it["index"])]
            t = PiiType(it["pii_type"])
            out.append({
                "index": it["index"], "pii_type": t.value, "family": FAMILY[t],
                "score": round(float(it["score"]), 4), "reason": it["reason"],
                "context": {
                    "before": text[max(0, sp.start - CONTEXT_CHARS) : sp.start],
                    "text": text[sp.start : sp.end],
                    "after": text[sp.end : sp.end + CONTEXT_CHARS],
                },
            })  # fmt: skip
        return {"items": out}

    def status(self, scan_id: str) -> dict[str, Any]:
        s = self._get(scan_id)
        err = None
        if s.status == "failed":
            code = s.error_code or "internal"
            msg = MESSAGES.get(code, MESSAGES["internal"])[1]
            if code == "internal":
                msg = "Something went wrong while scanning. Try again."
            err = {"code": code, "message": msg, "step": s.step}
        return {
            "id": s.id, "filename": s.filename, "format": s.format, "status": s.status,
            "step": s.step, "step_label": STEP_LABEL[s.step], "round": s.round,
            "max_rounds": MAX_ROUNDS_DEFAULT, "created_at": s.created_at,
            "updated_at": s.updated_at, "finished_at": s.finished_at, "expires_at": s.expires_at,
            "review": self._review(s), "risk": _risk(s), "error": err,
        }  # fmt: skip

    def is_open(self, scan_id: str) -> bool:
        s = self.repo.get(scan_id)
        return s is not None and s.status in ("queued", "running")

    # ---- 4.8 answers ----

    def answer(self, scan_id: str, answers: list[dict[str, Any]]) -> ScanRow:
        s = self._get(scan_id)
        if s.status != "needs_review":
            raise AppError("not_waiting_for_review")
        snap = self.c.reader.get_state(cfg(s.id))
        if not snap.interrupts:
            raise AppError("not_waiting_for_review")
        pending = {int(it["index"]) for it in snap.interrupts[0].value["items"]}
        given = [int(a["index"]) for a in answers]
        if sorted(given) != sorted(pending) or len(set(given)) != len(given):
            raise AppError("invalid_answers", field="answers")
        clean = [
            {
                "index": int(a["index"]),
                "verdict": a["verdict"],
                **({"pii_type": a["pii_type"]} if a.get("pii_type") else {}),
            }  # fmt: skip
            for a in answers
        ]
        WorkerRepo(self.c.db).set_state(s.id, "queued", clock.iso(clock.now()))
        self.c.enqueue(s.id, clean)
        return self._get(scan_id)

    # ---- 4.9 result ----

    def _decisions(self, s: ScanRow) -> list[DecisionRow]:
        if s.status != "done":
            raise AppError("scan_not_done")
        return self.repo.decisions(s.id)

    def result(self, scan_id: str) -> dict[str, Any]:
        s = self._get(scan_id)
        ds = self._decisions(s)
        try:
            _, doc = parse_original(self.c, s)
        except ScanFailedError as e:
            raise AppError("file_unreadable") from e
        items = [
            Item(
                d.idx,
                d.round,
                d.start_offset,
                d.end_offset,
                PiiType(d.pii_type),
                Action(d.action),
                d.token,
            )  # fmt: skip
            for d in ds
        ]
        rb = rebuild(doc, items)
        return {
            "id": s.id,
            "rounds": s.round,
            "risk": _risk(s),
            "original_text": doc.text,
            "items": [
                {
                    "idx": d.idx,
                    "round": d.round,
                    "start": d.start_offset,
                    "end": d.end_offset,
                    "pii_type": d.pii_type,
                    "family": FAMILY[PiiType(d.pii_type)],
                    "score": d.score,
                    "sources": d.sources.split("+"),
                    "action": d.action,
                    "action_label": ACTION_LABEL[Action(d.action)],
                    "reason": d.reason,
                    "reason_text": REASON_TEXT[d.reason] if d.round == 1 else LATER_ROUND_TEXT,
                    "token": d.token,
                    "output": rb.outputs.get(d.idx, ""),
                }  # fmt: skip
                for d in ds
            ],
            "cleaned_segments": rb.segments(),
        }

    # ---- 4.10 download ----

    def download(self, scan_id: str, kind: str) -> Download:
        s = self._get(scan_id)
        ds = self._decisions(s)
        short = s.id.split("-")[0]
        if kind == "report":
            counts = Counter(f"{d.pii_type}:{d.action}" for d in ds)
            body = {
                "report_version": 1, "scan_id": s.id, "model_version": s.model_version,
                "created_at": s.created_at, "finished_at": s.finished_at, "rounds": s.round,
                "risk": _risk(s), "counts": dict(sorted(counts.items())),
                "items": [
                    {"idx": d.idx, "round": d.round, "start": d.start_offset,
                     "end": d.end_offset, "pii_type": d.pii_type, "action": d.action,
                     "reason": d.reason, "token": d.token}  # fmt: skip
                    for d in ds
                ],
            }  # fmt: skip
            data = json.dumps(body, indent=2).encode()
            return Download(data, "application/json", f"report-{short}.json")
        meta = self.repo.file(s.id, "cleaned")
        if meta is None:
            raise AppError("scan_not_done")
        try:
            data = self.c.files.read(s.id, "cleaned", meta.stored)
        except Exception as e:
            raise AppError("storage_unavailable") from e
        ext = "txt" if s.format == "pdf" else s.format
        return Download(data, meta.content_type, f"cleaned-{short}.{ext}")

    # ---- 4.11 retry, 4.12 delete ----

    def retry(self, scan_id: str) -> ScanRow:
        s = self._get(scan_id)
        if s.status != "failed":
            raise AppError("scan_not_failed")
        WorkerRepo(self.c.db).set_state(s.id, "queued", clock.iso(clock.now()))
        self.c.enqueue(s.id)
        return self._get(scan_id)

    def delete(self, scan_id: str) -> None:
        s = self._get(scan_id)
        if s.status in ("queued", "running"):
            raise AppError("scan_running")
        w = WorkerRepo(self.c.db)
        with self.c.db.transaction():
            tokens = w.tokens_of(s.id)
            w.delete_scan(s.id)
            # A running scan may have stored vault rows it has not referenced yet; then
            # retention removes the unused ones later instead (DATABASE 10.3).
            if running_count(self.c.db) == 0:
                w.delete_unused_vault(tokens, clock.iso(clock.now() + clock.timedelta(seconds=1)))
        self.c.files.delete_scan(s.id)
        self.c.saver.delete_thread(s.id)
