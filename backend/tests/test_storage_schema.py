"""Schema, migrations and constraints (DATABASE 3, 9; IMPLEMENTATION_PLAN P2)."""

import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import exc, text

from app.detectors.types import PiiType
from app.fusion.risk import RiskLevel
from app.policy.actions import Action
from app.storage import schema_sql as sch
from app.storage.db import Database, downgrade, migrate

HASH60 = "$2b$12$" + "a" * 53
NOW = "2026-11-19T10:00:00.000Z"
LATER = "2026-11-26T10:00:00.000Z"


_open: list[sqlite3.Connection] = []


@pytest.fixture(autouse=True)
def _close_raw() -> Iterator[None]:
    yield
    while _open:
        _open.pop().close()


def raw(tmp: Path) -> sqlite3.Connection:
    c = sqlite3.connect(tmp / "app.db")
    c.execute("PRAGMA foreign_keys = ON")
    _open.append(c)
    return c


def names(c: sqlite3.Connection, kind: str) -> set[str]:
    q = "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE 'sqlite_%'"
    return {r[0] for r in c.execute(q, (kind,))}


def test_upgrade_creates_everything(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    assert names(c, "table") == set(sch.TABLE_NAMES) | {"alembic_version"}
    assert names(c, "index") >= {
        "scans_owner_created", "scans_expires", "sessions_expires", "sessions_user",
        "decisions_token",
    }  # fmt: skip
    assert names(c, "trigger") == {"audit_no_update", "audit_no_delete"}
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    for t in sch.TABLE_NAMES:  # every table is STRICT
        sql = c.execute("SELECT sql FROM sqlite_master WHERE name = ?", (t,)).fetchone()[0]
        assert sql.rstrip().endswith("STRICT"), t


def test_down_then_up_again(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    downgrade(tmp_path)
    assert names(raw(tmp_path), "table") == {"alembic_version"}
    migrate(tmp_path, backup=False)
    assert set(sch.TABLE_NAMES) <= names(raw(tmp_path), "table")


def test_migrate_backs_up_existing_db(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    migrate(tmp_path)  # second run: database exists
    assert (tmp_path / "backups" / "pre-migrate.db").stat().st_size > 0


def test_enums_match_python() -> None:
    """The CHECK lists and the domain enums must never drift apart."""
    assert set(sch.PII_TYPES) == {t.value for t in PiiType}
    assert set(sch.ACTIONS) == {a.value for a in Action}
    assert set(sch.RISK_LEVELS) == {r.value for r in RiskLevel}


def user(c: sqlite3.Connection, email: str = "a@x.io") -> int:
    cur = c.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                    (email, HASH60, NOW))  # fmt: skip
    return int(cur.lastrowid or 0)


def scan(c: sqlite3.Connection, owner: int, **kw: object) -> str:
    sid = str(uuid.uuid4())
    row = {"id": sid, "owner_id": owner, "filename": "f.txt", "format": "txt",
           "created_at": NOW, "updated_at": NOW, "expires_at": LATER, **kw}  # fmt: skip
    cols = ", ".join(row)
    c.execute(f"INSERT INTO scans ({cols}) VALUES ({', '.join('?' * len(row))})",
              tuple(row.values()))  # fmt: skip
    return sid


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO users (email, password_hash, created_at) VALUES ('nope', '{h}', '{n}')",
        "INSERT INTO users (email, password_hash, created_at) VALUES ('b@x.io', 'short', '{n}')",
        "INSERT INTO users (email, password_hash, role, created_at) "
        "VALUES ('c@x.io', '{h}', 'root', '{n}')",
        "INSERT INTO users (email, password_hash, created_at) VALUES ('A@X.IO', '{h}', '{n}')",
    ],
)
def test_user_checks(tmp_path: Path, sql: str) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    user(c)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute(sql.format(h=HASH60, n=NOW))


@pytest.mark.parametrize(
    "kw",
    [
        {"format": "exe"},
        {"status": "weird"},
        {"step": 6},
        {"round": 4},
        {"status": "done"},  # done needs risk fields + finished_at
        {"status": "failed", "finished_at": NOW},  # failed needs error_code
        {"status": "running", "finished_at": NOW},  # open scans have no finished_at
        {"expires_at": "2026-01-01T00:00:00.000Z"},  # expires before created
        {"risk_clues": "{not json"},
        {"id": "short"},
    ],
)
def test_scan_checks(tmp_path: Path, kw: dict[str, object]) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        scan(c, user(c), **kw)


def test_done_scan_ok_and_cascade(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    u = user(c)
    sid = scan(c, u, status="done", risk_level="LOW", est_matches=1.0, risk_clues="[]",
               finished_at=NOW)  # fmt: skip
    c.execute("INSERT INTO scan_files VALUES (?, 'original', 'text/plain', 3, 'k1', ?, ?)",
              (sid, b"\0" * 12, NOW))  # fmt: skip
    c.execute("INSERT INTO decisions VALUES (?, 0, 1, 0, 4, 'EMAIL', 0.9, 'regex', 'redact', "
              "'utility', NULL)", (sid,))  # fmt: skip
    with pytest.raises(sqlite3.IntegrityError):  # owner with scans cannot be deleted
        c.execute("DELETE FROM users WHERE id = ?", (u,))
    c.execute("DELETE FROM scans WHERE id = ?", (sid,))
    assert c.execute("SELECT count(*) FROM scan_files").fetchone()[0] == 0
    assert c.execute("SELECT count(*) FROM decisions").fetchone()[0] == 0


@pytest.mark.parametrize(
    "values",
    [
        "(?, 0, 1, 4, 4, 'EMAIL', 0.9, 'regex', 'redact', 'utility', NULL)",  # empty span
        "(?, 0, 1, 0, 4, 'SSN', 0.9, 'regex', 'redact', 'utility', NULL)",  # bad type
        "(?, 0, 1, 0, 4, 'EMAIL', 1.5, 'regex', 'redact', 'utility', NULL)",  # score > 1
        "(?, 0, 1, 0, 4, 'EMAIL', 0.9, 'regex', 'pseudonymize', 'utility', NULL)",  # no token
        "(?, 0, 1, 0, 4, 'EMAIL', 0.9, 'regex', 'redact', 'leak', NULL)",  # bad reason
        "(?, 0, 1, 0, 4, 'EMAIL', 0.9, 'regex', 'pseudonymize', 'utility', 'EMAIL_abcdef')",
    ],
)
def test_decision_checks(tmp_path: Path, values: str) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    sid = scan(c, user(c))
    with pytest.raises(sqlite3.IntegrityError):  # last case: token not in tokens (FK)
        c.execute(f"INSERT INTO decisions VALUES {values}", (sid,))


def test_token_and_vault_checks(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO tokens VALUES ('email_abc123', ?, 'k', ?)", ("a" * 64, NOW))
    c.execute("INSERT INTO tokens VALUES ('EMAIL_abc123', ?, 'k', ?)", ("a" * 64, NOW))
    with pytest.raises(sqlite3.IntegrityError):  # same mac + key twice
        c.execute("INSERT INTO tokens VALUES ('EMAIL_abc1234', ?, 'k', ?)", ("a" * 64, NOW))
    with pytest.raises(sqlite3.IntegrityError):  # vault row needs a token
        c.execute("INSERT INTO vault VALUES ('PHONE_abc123', 'PHONE', 'k', ?, x'00', ?)",
                  (b"\0" * 12, NOW))  # fmt: skip


def test_audit_log_is_append_only(tmp_path: Path) -> None:
    migrate(tmp_path, backup=False)
    c = raw(tmp_path)
    c.execute("INSERT INTO audit_log VALUES (0, ?, 'system', 'retention', '{}', ?, ?, 'k', ?)",
              (NOW, "a" * 64, "0" * 64, "b" * 64))  # fmt: skip
    for sql in ("UPDATE audit_log SET actor = 'user:1'", "DELETE FROM audit_log"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            c.execute(sql)
    with pytest.raises(sqlite3.IntegrityError):  # bad actor
        c.execute("INSERT INTO audit_log VALUES (1, ?, 'root', 'retention', '{}', ?, ?, 'k', ?)",
                  (NOW, "a" * 64, "b" * 64, "c" * 64))  # fmt: skip


def test_transaction_rolls_back_and_nests(db: Database) -> None:
    with pytest.raises(RuntimeError), db.transaction() as c:
        c.execute(text("INSERT INTO users (email, password_hash, created_at) "
                       "VALUES ('z@x.io', :h, :n)"), {"h": HASH60, "n": NOW})  # fmt: skip
        with db.transaction() as inner:
            assert inner is c  # joins the outer transaction
        raise RuntimeError
    with db.transaction() as c:
        assert c.execute(text("SELECT count(*) FROM users")).scalar_one() == 0


def test_engine_pragmas(db: Database) -> None:
    with db.transaction() as c:
        assert c.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
        assert c.execute(text("PRAGMA secure_delete")).scalar_one() == 1
        with pytest.raises(exc.IntegrityError):
            c.execute(text("INSERT INTO sessions VALUES (:h, 999, :n, :n, :n)"),
                      {"h": b"\0" * 32, "n": NOW})  # fmt: skip


def test_backup_is_a_usable_copy(db: Database, tmp_path: Path) -> None:
    db.backup_to(tmp_path / "b" / "app.db")
    c = raw(tmp_path / "b")
    assert c.execute("SELECT count(*) FROM users").fetchone()[0] == 0
