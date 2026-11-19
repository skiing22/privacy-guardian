"""Unscoped scan access for the scan worker, scan services' worker-side steps and the
retention job ONLY. The API layer must never import this (scripts/check_layers.py)."""

import json

from sqlalchemy import text

from app.storage.db import Database
from app.storage.rows import DECISION_COLUMNS, SCAN_COLUMNS, DecisionRow, FileRow, ScanRow


class WorkerRepo:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, scan_id: str) -> ScanRow | None:
        with self.db.transaction() as c:
            r = c.execute(text(f"SELECT {SCAN_COLUMNS} FROM scans WHERE id = :id"),
                          {"id": scan_id}).first()  # fmt: skip
        return ScanRow.from_row(r) if r else None

    def open_ids(self) -> list[str]:
        """Scans to put back in the queue after a restart (oldest first)."""
        with self.db.transaction() as c:
            rows = c.execute(text("SELECT id FROM scans WHERE status IN ('queued', 'running') "
                                  "ORDER BY created_at")).all()  # fmt: skip
        return [r[0] for r in rows]

    def set_state(self, scan_id: str, status: str, now: str, step: int | None = None,
                  round_: int | None = None) -> None:  # fmt: skip
        with self.db.transaction() as c:
            c.execute(
                text("UPDATE scans SET status = :s, updated_at = :now, "
                     "step = coalesce(:st, step), round = coalesce(:r, round), "
                     "error_code = NULL, finished_at = NULL WHERE id = :id"),
                {"s": status, "now": now, "st": step, "r": round_, "id": scan_id},
            )  # fmt: skip

    def put_file(self, scan_id: str, kind: str, content_type: str, size: int, key_id: str,
                 nonce: bytes, now: str) -> None:  # fmt: skip
        with self.db.transaction() as c:
            c.execute(
                text("INSERT INTO scan_files (scan_id, kind, content_type, size_bytes, key_id, "
                     "nonce, created_at) VALUES (:id, :k, :ct, :sz, :kid, :n, :now) "
                     "ON CONFLICT (scan_id, kind) DO UPDATE SET content_type = :ct, "
                     "size_bytes = :sz, key_id = :kid, nonce = :n, created_at = :now"),
                {"id": scan_id, "k": kind, "ct": content_type, "sz": size, "kid": key_id,
                 "n": nonce, "now": now},
            )  # fmt: skip

    def replace_decisions(self, scan_id: str, rows: list[DecisionRow]) -> None:
        with self.db.transaction() as c:
            c.execute(text("DELETE FROM decisions WHERE scan_id = :id"), {"id": scan_id})
            if rows:
                c.execute(
                    text(f"INSERT INTO decisions ({DECISION_COLUMNS}) VALUES (:scan_id, :idx, "
                         ":round, :start_offset, :end_offset, :pii_type, :score, :sources, "
                         ":action, :reason, :token)"),
                    [r.__dict__ for r in rows],
                )  # fmt: skip

    def finish(  # noqa: PLR0913
        self, scan_id: str, risk_level: str, est_matches: float, clues: list[str],
        unresolved: int, rounds: int, model_version: str | None, now: str,
    ) -> None:  # fmt: skip
        with self.db.transaction() as c:
            c.execute(
                text("UPDATE scans SET status = 'done', step = 5, round = :r, risk_level = :l, "
                     "est_matches = :m, risk_clues = :c, unresolved_leaks = :u, "
                     "model_version = :mv, error_code = NULL, updated_at = :now, "
                     "finished_at = :now WHERE id = :id"),
                {"r": rounds, "l": risk_level, "m": est_matches, "c": json.dumps(clues),
                 "u": unresolved, "mv": model_version, "now": now, "id": scan_id},
            )  # fmt: skip

    def fail(self, scan_id: str, code: str, now: str) -> None:
        with self.db.transaction() as c:
            c.execute(
                text(
                    "UPDATE scans SET status = 'failed', error_code = :c, updated_at = :now, "
                    "finished_at = :now WHERE id = :id"
                ),
                {"c": code, "now": now, "id": scan_id},
            )

    def tokens_of(self, scan_id: str) -> set[str]:
        with self.db.transaction() as c:
            rows = c.execute(text("SELECT DISTINCT token FROM decisions WHERE scan_id = :id "
                                  "AND token IS NOT NULL"), {"id": scan_id}).all()  # fmt: skip
        return {r[0] for r in rows}

    def delete_scan(self, scan_id: str) -> None:
        with self.db.transaction() as c:
            c.execute(text("DELETE FROM scans WHERE id = :id"), {"id": scan_id})

    def delete_unused_vault(self, tokens: set[str] | None, older_than: str) -> int:
        """Vault rows no decision references (DATABASE 3.7). `tokens` limits the check to
        those tokens (scan delete); None checks every row older than `older_than`, so a scan
        still being written never loses its entries (retention)."""
        sql = ("DELETE FROM vault WHERE created_at < :old AND NOT EXISTS "
               "(SELECT 1 FROM decisions d WHERE d.token = vault.token)")  # fmt: skip
        params: dict[str, object] = {"old": older_than}
        if tokens is not None:
            sql += " AND token IN (SELECT value FROM json_each(:toks))"
            params["toks"] = json.dumps(sorted(tokens))
        with self.db.transaction() as c:
            return c.execute(text(sql), params).rowcount

    def expired_ids(self, now: str) -> list[str]:
        with self.db.transaction() as c:
            rows = c.execute(text("SELECT id FROM scans WHERE expires_at <= :n"), {"n": now}).all()
        return [r[0] for r in rows]

    def all_ids(self) -> set[str]:
        with self.db.transaction() as c:
            return {r[0] for r in c.execute(text("SELECT id FROM scans")).all()}

    def decisions(self, scan_id: str) -> list[DecisionRow]:
        with self.db.transaction() as c:
            rows = c.execute(text(f"SELECT {DECISION_COLUMNS} FROM decisions WHERE scan_id = :id "
                                  "ORDER BY idx"), {"id": scan_id}).all()  # fmt: skip
        return [DecisionRow(*r) for r in rows]


def file_meta(db: Database, scan_id: str, kind: str) -> FileRow | None:
    """Unscoped file metadata (worker only)."""
    with db.transaction() as c:
        r = c.execute(
            text("SELECT scan_id, kind, content_type, size_bytes, key_id, nonce FROM scan_files "
                 "WHERE scan_id = :id AND kind = :k"),
            {"id": scan_id, "k": kind},
        ).first()  # fmt: skip
    return FileRow(r[0], r[1], r[2], r[3], r[4], bytes(r[5])) if r else None


def running_count(db: Database) -> int:
    with db.transaction() as c:
        return int(
            c.execute(text("SELECT count(*) FROM scans WHERE status = 'running'")).scalar_one()
        )
