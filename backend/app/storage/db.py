"""SQLite engine, transactions and migrations (DATABASE.md 1, 9).

- Every connection: WAL, foreign keys, busy timeout, secure_delete (DATABASE 1, 7.2).
- Every transaction is `BEGIN IMMEDIATE`: it takes the write lock up front, so two writers
  never deadlock while upgrading a read lock, and the audit chain can never fork.
- `Database.transaction()` sets the current connection in a context variable. Stores called
  inside it (vault, tokens, audit, beliefs) join that same transaction, so a service can
  commit "decisions + scan done + audit record" all or nothing (DATABASE 3.10).
"""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, event

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_current: ContextVar[Connection | None] = ContextVar("pg_db_conn", default=None)


def now_iso() -> str:
    """UTC ISO 8601 with milliseconds and Z: the one timestamp format (DATABASE 1.1)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def db_url(data_dir: Path) -> str:
    return f"sqlite:///{data_dir / 'app.db'}"


def make_engine(url: str | None = None) -> Engine:
    if url is None:
        from app.config import get_settings  # only when no url is given (alembic CLI)

        data_dir = get_settings().data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        url = db_url(data_dir)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 5})

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn: sqlite3.Connection, _rec: Any) -> None:
        dbapi_conn.isolation_level = None  # SQLAlchemy emits BEGIN itself (below)
        cur = dbapi_conn.cursor()
        for pragma in (
            "journal_mode=WAL", "foreign_keys=ON", "busy_timeout=5000",
            "synchronous=NORMAL", "secure_delete=ON",
        ):  # fmt: skip
            cur.execute(f"PRAGMA {pragma}")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


class Database:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def at(cls, data_dir: Path) -> "Database":
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(make_engine(db_url(data_dir)))

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """One transaction; nested calls (and stores) reuse the outer one."""
        outer = _current.get()
        if outer is not None:
            yield outer
            return
        with self.engine.begin() as conn:
            token = _current.set(conn)
            try:
                yield conn
            finally:
                _current.reset(token)

    def backup_to(self, target: Path) -> None:
        """Consistent online copy of the database while it is in use (DATABASE 10.1)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = self.engine.raw_connection()
        try:
            dst = sqlite3.connect(target)
            try:
                raw.driver_connection.backup(dst)  # type: ignore[union-attr]
            finally:
                dst.close()
        finally:
            raw.close()


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def migrate(data_dir: Path, revision: str = "head", backup: bool = True) -> None:
    """Back up (if a database exists), then upgrade to `revision` (DATABASE 9.1)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "app.db"
    if backup and db_file.exists() and db_file.stat().st_size > 0:
        engine = make_engine(db_url(data_dir))
        try:
            Database(engine).backup_to(data_dir / "backups" / "pre-migrate.db")
        finally:
            engine.dispose()
    command.upgrade(alembic_config(db_url(data_dir)), revision)


def downgrade(data_dir: Path, revision: str = "base") -> None:
    command.downgrade(alembic_config(db_url(data_dir)), revision)


def copy_files(src: Path, dst: Path) -> None:
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)
