"""Tamper-evident audit log: an HMAC hash chain (FR-26, FR-27, ADR-0003).

    mac_i = HMAC(K2, canonical(seq, ts, actor, event, payload_hash, prev_mac, kid))
    prev_mac of record i = mac_{i-1}  (genesis: 64 zeros)

Change, delete, insert or reorder any record and every mac from there on stops matching.
Without K2 an attacker cannot recompute the chain.

Known limit (ADR-0003): someone who steals K2 can rebuild the whole chain. An ANCHOR
(latest seq + mac, copied somewhere the server cannot rewrite) catches that: a rebuilt
chain will not match the anchored mac. Anchors also catch silent truncation of the tail.

NFR-04: payloads must never contain raw PII, only tokens, types, counts and ids.
"""

import hashlib
import hmac
import json
import threading
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from app.crypto.keys import KeySet

GENESIS = "0" * 64


def canonical(obj: Any) -> bytes:
    """Same object -> same bytes, always (sorted keys, no spaces). Verify depends on it."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass(frozen=True)
class AuditRecord:
    seq: int
    ts: str
    actor: str
    event: str
    payload: dict[str, Any]
    payload_hash: str
    prev_mac: str
    kid: str
    mac: str

    def body(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("mac")
        d.pop("payload")  # the mac covers its hash; the payload itself can be archived
        return d


@dataclass(frozen=True)
class Anchor:
    seq: int
    mac: str


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    checked: int
    first_bad_seq: int | None = None
    reason: str = ""


class AuditStore(Protocol):
    def append(self, rec: AuditRecord) -> None: ...
    def all(self) -> list[AuditRecord]: ...


class InMemoryAuditStore:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def append(self, rec: AuditRecord) -> None:
        self.records.append(rec)

    def all(self) -> list[AuditRecord]:
        return list(self.records)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _mac(key: bytes, body: dict[str, Any]) -> str:
    return hmac.new(key, canonical(body), hashlib.sha256).hexdigest()


class AuditLog:
    def __init__(
        self, keys: KeySet, store: AuditStore | None = None, clock: Callable[[], str] = _now
    ) -> None:
        self.keys, self.clock = keys, clock
        self.store: AuditStore = store or InMemoryAuditStore()
        # Read-last + append must not interleave between threads (one process, D17).
        # Across processes the SQL primary key on seq rejects a fork instead.
        self._lock = threading.Lock()

    def append(self, actor: str, event: str, payload: dict[str, Any]) -> AuditRecord:
        # Lock order is always: the store's transaction (database write lock) first, then
        # this lock. Taking them the other way round could make two threads wait on each other.
        atomic = getattr(self.store, "atomic", None)
        with atomic() if atomic else nullcontext(), self._lock:
            return self._append(actor, event, payload)

    def _append(self, actor: str, event: str, payload: dict[str, Any]) -> AuditRecord:
        recs = self.store.all()
        prev = recs[-1].mac if recs else GENESIS
        kid, key = self.keys.current
        payload_hash = hashlib.sha256(canonical(payload)).hexdigest()
        rec = AuditRecord(
            seq=len(recs), ts=self.clock(), actor=actor, event=event, payload=payload,
            payload_hash=payload_hash, prev_mac=prev, kid=kid, mac="",
        )  # fmt: skip
        rec = replace(rec, mac=_mac(key, rec.body()))
        self.store.append(rec)
        return rec

    def anchor(self) -> Anchor | None:
        recs = self.store.all()
        return Anchor(recs[-1].seq, recs[-1].mac) if recs else None

    def verify(self, anchor: Anchor | None = None) -> VerifyResult:
        recs = self.store.all()
        prev = GENESIS
        for i, r in enumerate(recs):
            if r.seq != i:
                return VerifyResult(False, i, i, "sequence gap or reorder")
            if r.prev_mac != prev:
                return VerifyResult(False, i, r.seq, "chain broken (record removed or inserted)")
            if hashlib.sha256(canonical(r.payload)).hexdigest() != r.payload_hash:
                return VerifyResult(False, i, r.seq, "payload changed")
            try:
                key = self.keys.get(r.kid)
            except ValueError:
                return VerifyResult(False, i, r.seq, f"unknown key id {r.kid}")
            if not hmac.compare_digest(_mac(key, r.body()), r.mac):
                return VerifyResult(False, i, r.seq, "mac mismatch (record edited)")
            prev = r.mac
        if anchor is not None:
            if anchor.seq >= len(recs):
                return VerifyResult(
                    False, len(recs), anchor.seq, "log is shorter than anchor (truncated)"
                )
            if not hmac.compare_digest(recs[anchor.seq].mac, anchor.mac):
                return VerifyResult(
                    False, len(recs), anchor.seq, "does not match anchor (chain rewritten)"
                )
        return VerifyResult(True, len(recs))
