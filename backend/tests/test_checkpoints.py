"""Encrypted SQLite checkpoints: restart/resume, nothing readable on disk, tamper fails."""

import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app.crypto.keys import KeySet
from app.detectors.types import PiiType
from app.graph.build import build_graph, pending_review, result_of, resume_scan, start_scan
from app.graph.checkpoints import (
    AesGcmCipher,
    CheckpointIntegrityError,
    make_encrypted_serde,
    open_checkpointer,
)
from tests.test_graph import deps

T = PiiType
TEXT = "Thanks Priya, call 98470 12345"


def ks(*kids: str) -> KeySet:
    return KeySet(tuple((k, secrets.token_bytes(32)) for k in kids))


def test_resume_after_restart_with_sqlite(tmp_path: Path) -> None:
    keys = ks("s1")
    path = tmp_path / "checkpoints.db"
    saver = open_checkpointer(path, keys)
    app1 = build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver)
    assert pending_review(start_scan(app1, TEXT, "scan-1")) is not None
    saver.conn.close()  # "server restart"

    saver2 = open_checkpointer(path, keys)
    app2 = build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver2)
    res = result_of(resume_scan(app2, "scan-1", [{"index": 0, "verdict": "protect"}]))
    assert "Priya" not in res.output and "PERSON_1" in res.output
    saver2.delete_thread("scan-1")
    assert saver2.get_tuple({"configurable": {"thread_id": "scan-1"}}) is None
    saver2.conn.close()


def test_no_plain_text_on_disk(tmp_path: Path) -> None:
    saver = open_checkpointer(tmp_path / "c.db", ks("s1"))
    app = build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver)
    start_scan(app, TEXT, "scan-2")
    saver.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    saver.conn.close()
    blob = (tmp_path / "c.db").read_bytes()
    assert b"Priya" not in blob and b"98470" not in blob


def test_wrong_key_or_tamper_fails(tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    saver = open_checkpointer(path, ks("s1"))
    start_scan(build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver), TEXT, "s")
    saver.conn.close()
    other = open_checkpointer(path, ks("s1"))  # same kid, different bytes
    with pytest.raises(CheckpointIntegrityError):
        other.get_tuple({"configurable": {"thread_id": "s"}})
    other.conn.close()


def test_rotation_reads_old_checkpoints() -> None:
    old = ks("s1")
    new = KeySet((*old.keys, ("s2", secrets.token_bytes(32))))
    name, ct = AesGcmCipher(old).encrypt(b"state")
    assert name == "aesgcm:s1"
    assert AesGcmCipher(new).decrypt(name, ct) == b"state"
    assert AesGcmCipher(new).encrypt(b"x")[0] == "aesgcm:s2"


def test_plain_rows_are_refused() -> None:
    serde = make_encrypted_serde(ks("s1"))
    typ, data = serde.dumps_typed({"a": 1})
    assert "+aesgcm:s1" in typ and serde.loads_typed((typ, data)) == {"a": 1}
    plain = serde.serde.dumps_typed({"a": 1})  # no cipher name: someone planted it
    with pytest.raises(CheckpointIntegrityError):
        serde.loads_typed(plain)
    with pytest.raises(CheckpointIntegrityError):
        AesGcmCipher(ks("s1")).decrypt("rot13", b"x")


def test_checkpoint_db_is_separate_file(tmp_path: Path) -> None:
    saver = open_checkpointer(tmp_path / "checkpoints.db", ks("s1"))
    saver.conn.close()
    with closing(sqlite3.connect(tmp_path / "checkpoints.db")) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "checkpoints" in names
