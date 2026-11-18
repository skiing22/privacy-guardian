"""SQL implementations of the domain's store interfaces (ARCHITECTURE 3.2).

Each method runs in `Database.transaction()`, so it joins a service's open transaction
when there is one, and is its own transaction otherwise.
"""

import json
from contextlib import AbstractContextManager
from dataclasses import asdict
from typing import Any

from sqlalchemy import text

from app.crypto.audit import AuditRecord
from app.crypto.tokens import TokenEntry
from app.crypto.vault import VaultEntry
from app.detectors.types import PiiType
from app.policy.beliefs import Beta, TypeBelief, prior
from app.storage.db import Database, now_iso


class SqlBeliefStore:
    """One organisation per deployment (D3): `org` is accepted and ignored."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, org: str, t: PiiType) -> TypeBelief:
        with self.db.transaction() as c:
            r = c.execute(
                text("SELECT sens_alpha, sens_beta, prec_alpha, prec_beta FROM beliefs "
                     "WHERE pii_type = :t"), {"t": t.value},
            ).first()  # fmt: skip
        if r is None:
            return prior(t)
        return TypeBelief(Beta(r[0], r[1]), Beta(r[2], r[3]))

    def put(self, org: str, t: PiiType, b: TypeBelief) -> None:
        with self.db.transaction() as c:
            c.execute(
                text(
                    "INSERT INTO beliefs (pii_type, sens_alpha, sens_beta, prec_alpha, "
                    "prec_beta, updated_at) VALUES (:t, :sa, :sb, :pa, :pb, :now) "
                    "ON CONFLICT (pii_type) DO UPDATE SET sens_alpha = :sa, sens_beta = :sb, "
                    "prec_alpha = :pa, prec_beta = :pb, updated_at = :now"
                ),
                {"t": t.value, "sa": b.sensitivity.alpha, "sb": b.sensitivity.beta,
                 "pa": b.precision.alpha, "pb": b.precision.beta, "now": now_iso()},
            )  # fmt: skip

    def reset(self) -> int:
        with self.db.transaction() as c:
            return c.execute(text("DELETE FROM beliefs")).rowcount


class SqlTokenRegistry:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, token: str) -> TokenEntry | None:
        with self.db.transaction() as c:
            r = c.execute(
                text("SELECT full_mac, key_id FROM tokens WHERE token = :t"), {"t": token}
            ).first()
        return TokenEntry(r[0], r[1]) if r else None

    def put(self, token: str, entry: TokenEntry) -> None:
        with self.db.transaction() as c:
            c.execute(
                text("INSERT INTO tokens (token, full_mac, key_id, created_at) "
                     "VALUES (:t, :m, :k, :now)"),
                {"t": token, "m": entry.full_mac, "k": entry.kid, "now": now_iso()},
            )  # fmt: skip


class SqlVaultStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, token: str) -> VaultEntry | None:
        with self.db.transaction() as c:
            r = c.execute(
                text("SELECT token, pii_type, key_id, nonce, ciphertext FROM vault "
                     "WHERE token = :t"), {"t": token},
            ).first()  # fmt: skip
        return VaultEntry(r[0], r[1], r[2], bytes(r[3]), bytes(r[4])) if r else None

    def put(self, entry: VaultEntry) -> None:
        with self.db.transaction() as c:
            c.execute(
                text(
                    "INSERT INTO vault (token, pii_type, key_id, nonce, ciphertext, created_at) "
                    "VALUES (:t, :p, :k, :n, :c, :now) ON CONFLICT (token) DO NOTHING"
                ),
                {"t": entry.token, "p": entry.pii_type, "k": entry.kid, "n": entry.nonce,
                 "c": entry.ciphertext, "now": now_iso()},
            )  # fmt: skip


class SqlAuditStore:
    """Append-only (triggers block UPDATE/DELETE). `seq` is the primary key, so two
    writers that read the same tail cannot both append: the second insert fails."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def atomic(self) -> AbstractContextManager[Any]:
        """AuditLog wraps read-tail + append in this, so both see one consistent tail."""
        return self.db.transaction()

    def append(self, rec: AuditRecord) -> None:
        d = asdict(rec)
        d["payload"] = json.dumps(rec.payload, sort_keys=True, ensure_ascii=False)
        with self.db.transaction() as c:
            c.execute(
                text(
                    "INSERT INTO audit_log (seq, ts, actor, event, payload, payload_hash, "
                    "prev_mac, kid, mac) VALUES (:seq, :ts, :actor, :event, :payload, "
                    ":payload_hash, :prev_mac, :kid, :mac)"
                ),
                d,
            )

    def all(self) -> list[AuditRecord]:
        with self.db.transaction() as c:
            rows = c.execute(text(f"SELECT {_AUDIT_COLS} FROM audit_log ORDER BY seq")).all()
        return [_record(r) for r in rows]

    def page(self, before_seq: int | None, limit: int) -> list[AuditRecord]:
        """Newest first (API 4.17)."""
        sql = f"SELECT {_AUDIT_COLS} FROM audit_log"
        params: dict[str, object] = {"lim": limit}
        if before_seq is not None:
            sql += " WHERE seq < :b"
            params["b"] = before_seq
        with self.db.transaction() as c:
            rows = c.execute(text(sql + " ORDER BY seq DESC LIMIT :lim"), params).all()
        return [_record(r) for r in rows]


_AUDIT_COLS = "seq, ts, actor, event, payload, payload_hash, prev_mac, kid, mac"


def _record(r: Any) -> AuditRecord:
    return AuditRecord(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6], r[7], r[8])
