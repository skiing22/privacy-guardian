"""Repositories for API-facing services. Scan data is ALWAYS scoped by owner
(DATABASE 8): `ScanRepo` cannot be built without an owner id, and every query filters on it.
Unscoped access for the worker and retention lives in `worker_repo.py`, which the API
layer cannot import (scripts/check_layers.py)."""

from sqlalchemy import text

from app.detectors.types import PiiType
from app.policy.actions import Action
from app.storage.db import Database
from app.storage.rows import (
    DECISION_COLUMNS,
    SCAN_COLUMNS,
    DecisionRow,
    FileRow,
    ScanRow,
    UserRow,
)

USER_COLUMNS = "id, email, password_hash, role, is_active, created_at"


def _user(r: object) -> UserRow:
    m = r._mapping  # type: ignore[attr-defined]
    return UserRow(m["id"], m["email"], m["password_hash"], m["role"], bool(m["is_active"]),
                   m["created_at"])  # fmt: skip


class UserRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, email: str, password_hash: str, role: str, now: str) -> int:
        with self.db.transaction() as c:
            r = c.execute(
                text("INSERT INTO users (email, password_hash, role, created_at) "
                     "VALUES (:e, :h, :r, :now) RETURNING id"),
                {"e": email, "h": password_hash, "r": role, "now": now},
            ).one()  # fmt: skip
        return int(r[0])

    def by_email(self, email: str) -> UserRow | None:
        with self.db.transaction() as c:
            r = c.execute(
                text(f"SELECT {USER_COLUMNS} FROM users WHERE email = :e"), {"e": email}
            ).first()
        return _user(r) if r else None

    def by_id(self, user_id: int) -> UserRow | None:
        with self.db.transaction() as c:
            r = c.execute(
                text(f"SELECT {USER_COLUMNS} FROM users WHERE id = :i"), {"i": user_id}
            ).first()
        return _user(r) if r else None

    def count(self) -> int:
        with self.db.transaction() as c:
            return int(c.execute(text("SELECT count(*) FROM users")).scalar_one())

    def set_active(self, user_id: int, active: bool) -> None:
        with self.db.transaction() as c:
            c.execute(text("UPDATE users SET is_active = :a WHERE id = :i"),
                      {"a": int(active), "i": user_id})  # fmt: skip
            if not active:
                c.execute(text("DELETE FROM sessions WHERE user_id = :i"), {"i": user_id})

    def emails(self, ids: set[int]) -> dict[int, str]:
        if not ids:
            return {}
        with self.db.transaction() as c:
            rows = c.execute(
                text("SELECT id, email FROM users WHERE id IN (SELECT value FROM json_each(:ids))"),
                {"ids": "[" + ",".join(str(i) for i in ids) + "]"},
            ).all()
        return {int(r[0]): r[1] for r in rows}


class SessionRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, id_hash: bytes, user_id: int, now: str, expires_at: str) -> None:
        with self.db.transaction() as c:
            c.execute(
                text("INSERT INTO sessions (id_hash, user_id, created_at, last_seen_at, "
                     "expires_at) VALUES (:h, :u, :now, :now, :exp)"),
                {"h": id_hash, "u": user_id, "now": now, "exp": expires_at},
            )  # fmt: skip

    def get(self, id_hash: bytes) -> tuple[str, str, str, UserRow] | None:
        """(created_at, last_seen_at, expires_at, user) or None."""
        with self.db.transaction() as c:
            r = c.execute(
                text(f"SELECT s.created_at, s.last_seen_at, s.expires_at, "
                     f"{', '.join('u.' + x.strip() for x in USER_COLUMNS.split(','))} "
                     "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id_hash = :h"),
                {"h": id_hash},
            ).first()  # fmt: skip
        if r is None:
            return None
        return r[0], r[1], r[2], UserRow(r[3], r[4], r[5], r[6], bool(r[7]), r[8])

    def touch(self, id_hash: bytes, last_seen_at: str, expires_at: str) -> None:
        with self.db.transaction() as c:
            c.execute(
                text("UPDATE sessions SET last_seen_at = :l, expires_at = :e WHERE id_hash = :h"),
                {"l": last_seen_at, "e": expires_at, "h": id_hash},
            )

    def delete(self, id_hash: bytes) -> None:
        with self.db.transaction() as c:
            c.execute(text("DELETE FROM sessions WHERE id_hash = :h"), {"h": id_hash})

    def delete_expired(self, now: str) -> int:
        with self.db.transaction() as c:
            return c.execute(
                text("DELETE FROM sessions WHERE expires_at <= :n"), {"n": now}
            ).rowcount


class RuleRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def all(self) -> dict[PiiType, tuple[Action, str]]:
        """type -> (action, updated_at)."""
        with self.db.transaction() as c:
            rows = c.execute(text("SELECT pii_type, action, updated_at FROM rules")).all()
        return {PiiType(r[0]): (Action(r[1]), r[2]) for r in rows}

    def replace(self, rules: dict[PiiType, Action], by: int, now: str) -> None:
        with self.db.transaction() as c:
            c.execute(text("DELETE FROM rules"))
            for t, a in rules.items():
                c.execute(
                    text("INSERT INTO rules (pii_type, action, updated_by, updated_at) "
                         "VALUES (:t, :a, :b, :now)"),
                    {"t": t.value, "a": a.value, "b": by, "now": now},
                )  # fmt: skip


class ScanRepo:
    """Owner-scoped: every query has `owner_id = :o`."""

    def __init__(self, db: Database, owner_id: int) -> None:
        self.db = db
        self.owner_id = owner_id

    def create(self, scan_id: str, filename: str, fmt: str, now: str, expires_at: str) -> None:
        with self.db.transaction() as c:
            c.execute(
                text("INSERT INTO scans (id, owner_id, filename, format, created_at, updated_at, "
                     "expires_at) VALUES (:id, :o, :f, :fmt, :now, :now, :exp)"),
                {"id": scan_id, "o": self.owner_id, "f": filename, "fmt": fmt, "now": now,
                 "exp": expires_at},
            )  # fmt: skip

    def get(self, scan_id: str) -> ScanRow | None:
        with self.db.transaction() as c:
            r = c.execute(
                text(f"SELECT {SCAN_COLUMNS} FROM scans WHERE id = :id AND owner_id = :o"),
                {"id": scan_id, "o": self.owner_id},
            ).first()
        return ScanRow.from_row(r) if r else None

    def page(self, status: str | None, before: tuple[str, str] | None, limit: int) -> list[ScanRow]:
        where = ["owner_id = :o"]
        params: dict[str, object] = {"o": self.owner_id, "lim": limit}
        if status:
            where.append("status = :s")
            params["s"] = status
        if before:
            where.append("(created_at < :bc OR (created_at = :bc AND id < :bi))")
            params["bc"], params["bi"] = before
        sql = (f"SELECT {SCAN_COLUMNS} FROM scans WHERE {' AND '.join(where)} "
               "ORDER BY created_at DESC, id DESC LIMIT :lim")  # fmt: skip
        with self.db.transaction() as c:
            return [ScanRow.from_row(r) for r in c.execute(text(sql), params).all()]

    def open_count(self) -> int:
        with self.db.transaction() as c:
            return int(c.execute(
                text("SELECT count(*) FROM scans WHERE owner_id = :o "
                     "AND status IN ('queued', 'running', 'needs_review')"),
                {"o": self.owner_id},
            ).scalar_one())  # fmt: skip

    def file(self, scan_id: str, kind: str) -> FileRow | None:
        with self.db.transaction() as c:
            r = c.execute(
                text("SELECT f.scan_id, f.kind, f.content_type, f.size_bytes, f.key_id, f.nonce "
                     "FROM scan_files f JOIN scans s ON s.id = f.scan_id "
                     "WHERE f.scan_id = :id AND f.kind = :k AND s.owner_id = :o"),
                {"id": scan_id, "k": kind, "o": self.owner_id},
            ).first()  # fmt: skip
        return FileRow(r[0], r[1], r[2], r[3], r[4], bytes(r[5])) if r else None

    def decisions(self, scan_id: str) -> list[DecisionRow]:
        with self.db.transaction() as c:
            rows = c.execute(
                text(f"SELECT {', '.join('d.' + x.strip() for x in DECISION_COLUMNS.split(','))} "
                     "FROM decisions d JOIN scans s ON s.id = d.scan_id "
                     "WHERE d.scan_id = :id AND s.owner_id = :o ORDER BY d.idx"),
                {"id": scan_id, "o": self.owner_id},
            ).all()  # fmt: skip
        return [DecisionRow(*r) for r in rows]
