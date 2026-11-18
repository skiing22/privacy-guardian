"""Store contract tests: the SQL stores behave exactly like the in-memory ones the
domain tests use (IMPLEMENTATION_PLAN P3), plus repos, owner scoping and file store."""

import secrets
import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import exc

from app.crypto.audit import AuditLog, InMemoryAuditStore
from app.crypto.keys import KeySet
from app.crypto.tokens import InMemoryTokenRegistry, Pseudonymizer, TokenEntry
from app.crypto.vault import InMemoryVaultStore, Vault, VaultEntry
from app.detectors.types import PiiType
from app.policy.actions import Action
from app.policy.beliefs import Beta, InMemoryBeliefStore, TypeBelief, prior
from app.storage.db import Database
from app.storage.files import EncryptedFileStore, FileIntegrityError
from app.storage.repos import RuleRepo, ScanRepo, SessionRepo, UserRepo
from app.storage.rows import DecisionRow
from app.storage.stores import SqlAuditStore, SqlBeliefStore, SqlTokenRegistry, SqlVaultStore
from app.storage.worker_repo import WorkerRepo

HASH60 = "$2b$12$" + "a" * 53
NOW = "2026-11-19T10:00:00.000Z"
LATER = "2026-11-26T10:00:00.000Z"


def ks(kid: str = "k1") -> KeySet:
    return KeySet(((kid, secrets.token_bytes(32)),))


Factory = Callable[[Database], Any]
BELIEFS: list[Factory] = [lambda d: InMemoryBeliefStore(), SqlBeliefStore]
TOKENS: list[Factory] = [lambda d: InMemoryTokenRegistry(), SqlTokenRegistry]
VAULTS: list[Factory] = [lambda d: InMemoryVaultStore(), SqlVaultStore]
AUDITS: list[Factory] = [lambda d: InMemoryAuditStore(), SqlAuditStore]
IDS = ["memory", "sql"]


@pytest.mark.parametrize("make", BELIEFS, ids=IDS)
def test_beliefs_contract(db: Database, make: Factory) -> None:
    s = make(db)
    assert s.get("org", PiiType.EMAIL) == prior(PiiType.EMAIL)
    b = TypeBelief(Beta(3.0, 2.0), Beta(5.0, 1.5))
    s.put("org", PiiType.EMAIL, b)
    s.put("org", PiiType.EMAIL, b)  # upsert
    assert s.get("org", PiiType.EMAIL) == b
    assert s.get("org", PiiType.PHONE) == prior(PiiType.PHONE)


@pytest.mark.parametrize("make", TOKENS, ids=IDS)
def test_pseudonymizer_same_on_both(db: Database, make: Factory) -> None:
    keys = KeySet((("t1", b"\x01" * 32),))
    reg = make(db)
    p = Pseudonymizer(keys, reg, min_hex=3)  # 3 hex: ~11 collisions in 300 values
    vals = [f"98470{i:05d}" for i in range(300)]
    toks = {v: p.token(PiiType.PHONE, v) for v in vals}
    assert p.collisions > 0
    assert len(set(toks.values())) == len(toks)  # every clash resolved
    again = Pseudonymizer(keys, make(db) if make is SqlTokenRegistry else reg, min_hex=3)
    assert all(again.token(PiiType.PHONE, v) == t for v, t in toks.items())  # stable


@pytest.mark.parametrize(("mv", "ma"), list(zip(VAULTS, AUDITS, strict=True)), ids=IDS)
def test_vault_and_audit_contract(db: Database, mv: Factory, ma: Factory) -> None:
    audit = AuditLog(ks("a1"), ma(db))
    if mv is SqlVaultStore:  # vault rows need a token row (FK)
        SqlTokenRegistry(db).put("PHONE_abc123", TokenEntry("f" * 64, "t1"))
    v = Vault(ks("v1"), audit, mv(db))
    v.put("PHONE_abc123", PiiType.PHONE, "9847012345")
    v.put("PHONE_abc123", PiiType.PHONE, "9847012345")  # idempotent
    assert v.reidentify("PHONE_abc123", "user:1", "admin", "fraud case 42 review") == "9847012345"
    with pytest.raises(Exception, match="only admins"):
        v.reidentify("PHONE_abc123", "user:2", "user", "fraud case 42 review")
    events = [r.event for r in audit.store.all()]
    assert events == ["reidentify", "reidentify_denied"]
    assert audit.verify().ok
    assert "9847012345" not in str(audit.store.all())  # NFR-04


def test_sql_audit_survives_reload_and_rejects_forks(db: Database) -> None:
    keys = ks("a1")
    log = AuditLog(keys, SqlAuditStore(db))
    for i in range(5):
        log.append("system", "retention", {"count": i})
    again = AuditLog(keys, SqlAuditStore(db))
    assert again.verify(log.anchor()).ok
    rec = again.store.all()[-1]
    with pytest.raises(exc.IntegrityError):  # same seq twice -> primary key stops a fork
        SqlAuditStore(db).append(rec)


def test_audit_lock_keeps_chain_under_threads(db: Database) -> None:
    log = AuditLog(ks("a1"), SqlAuditStore(db))

    def work() -> None:
        for _ in range(10):
            log.append("system", "retention", {"count": 1})

    ts = [threading.Thread(target=work) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert log.verify().ok and len(log.store.all()) == 40


def make_user(db: Database, email: str = "a@x.io", role: str = "user") -> int:
    return UserRepo(db).create(email, HASH60, role, NOW)


def test_user_and_session_repo(db: Database) -> None:
    users, sessions = UserRepo(db), SessionRepo(db)
    uid = make_user(db, "Ana@x.io")
    assert users.by_email("ana@X.IO") is not None  # emails compare case-insensitively
    assert users.count() == 1 and users.emails({uid}) == {uid: "Ana@x.io"}
    h = secrets.token_bytes(32)
    sessions.create(h, uid, NOW, LATER)
    got = sessions.get(h)
    assert got is not None and got[3].id == uid
    sessions.touch(h, LATER, LATER)
    assert sessions.delete_expired(LATER) == 1
    sessions.create(h, uid, NOW, LATER)
    users.set_active(uid, False)  # disabling a user ends their sessions
    assert sessions.get(h) is None
    u = users.by_id(uid)
    assert u is not None and not u.is_active


def test_rule_repo_replace(db: Database) -> None:
    uid = make_user(db, role="admin")
    rules = RuleRepo(db)
    rules.replace({PiiType.EMAIL: Action.MASK, PiiType.PAN: Action.REDACT}, uid, NOW)
    rules.replace({PiiType.EMAIL: Action.REDACT}, uid, NOW)
    assert {t: a for t, (a, _) in rules.all().items()} == {PiiType.EMAIL: Action.REDACT}


def new_scan(db: Database, owner: int) -> str:
    sid = str(uuid.uuid4())
    ScanRepo(db, owner).create(sid, "notes.txt", "txt", NOW, LATER)
    return sid


def test_scan_repo_is_owner_scoped(db: Database) -> None:
    a, b = make_user(db, "a@x.io"), make_user(db, "b@x.io")
    sid = new_scan(db, a)
    w = WorkerRepo(db)
    w.put_file(sid, "original", "text/plain", 10, "k1", b"\0" * 12, NOW)
    assert ScanRepo(db, a).get(sid) is not None
    mine, theirs = ScanRepo(db, a), ScanRepo(db, b)
    assert theirs.get(sid) is None
    assert theirs.page(None, None, 20) == []
    assert theirs.file(sid, "original") is None
    assert theirs.decisions(sid) == []
    assert mine.file(sid, "original") is not None and mine.open_count() == 1


def test_scan_paging_and_filter(db: Database) -> None:
    a = make_user(db)
    repo = ScanRepo(db, a)
    ids = []
    for i in range(5):
        sid = str(uuid.uuid4())
        repo.create(sid, f"f{i}.txt", "txt", f"2026-11-19T10:00:0{i}.000Z", LATER)
        ids.append(sid)
    first = repo.page(None, None, 2)
    assert [s.filename for s in first] == ["f4.txt", "f3.txt"]
    nxt = repo.page(None, (first[-1].created_at, first[-1].id), 10)
    assert [s.filename for s in nxt] == ["f2.txt", "f1.txt", "f0.txt"]
    assert repo.page("done", None, 10) == []


def test_worker_finish_fail_and_vault_cleanup(db: Database) -> None:
    a = make_user(db)
    w = WorkerRepo(db)
    sid, sid2 = new_scan(db, a), new_scan(db, a)
    assert w.open_ids() == [sid, sid2]
    w.set_state(sid, "running", NOW, step=2)
    reg, vault = SqlTokenRegistry(db), SqlVaultStore(db)
    for tok in ("PERSON_aaaaaa", "PERSON_bbbbbb"):
        reg.put(tok, TokenEntry(secrets.token_hex(32), "t1"))
        vault.put(VaultEntry(tok, "PERSON", "v1", b"\0" * 12, b"x"))
    w.replace_decisions(sid, [DecisionRow(sid, 0, 1, 0, 4, "PERSON", 0.9, "ner",
                                          "pseudonymize", "utility", "PERSON_aaaaaa")])  # fmt: skip
    w.finish(sid, "LOW", 1.0, ["clue"], 0, 1, "m1", NOW)
    done = w.get(sid)
    assert done is not None and done.status == "done" and done.risk_clues == ["clue"]
    w.fail(sid2, "parse_failed", NOW)
    assert w.open_ids() == []
    # a vault row still used by a decision is kept; the unused one goes
    assert w.delete_unused_vault(None, LATER) == 1
    assert vault.get("PERSON_aaaaaa") is not None and vault.get("PERSON_bbbbbb") is None
    assert w.tokens_of(sid) == {"PERSON_aaaaaa"}
    w.delete_scan(sid)
    assert w.delete_unused_vault({"PERSON_aaaaaa"}, LATER) == 1
    assert w.expired_ids(LATER) == [sid2]


def test_file_store_roundtrip_and_tamper(tmp_path: Path) -> None:
    keys = ks("s1")
    fs = EncryptedFileStore(tmp_path / "files", keys)
    meta = fs.write("scan-a", "original", b"Rahul 98470 12345")
    assert b"Rahul" not in fs.path("scan-a", "original").read_bytes()  # encrypted at rest
    assert fs.read("scan-a", "original", meta) == b"Rahul 98470 12345"
    # copied onto another scan -> fails (associated data binds scan id and kind)
    fs.path("scan-b", "original").write_bytes(fs.path("scan-a", "original").read_bytes())
    with pytest.raises(FileIntegrityError):
        fs.read("scan-b", "original", meta)
    data = bytearray(fs.path("scan-a", "original").read_bytes())
    data[0] ^= 1
    fs.path("scan-a", "original").write_bytes(bytes(data))
    with pytest.raises(FileIntegrityError):
        fs.read("scan-a", "original", meta)
    assert fs.scan_ids() == {"scan-a", "scan-b"}
    fs.delete_scan("scan-a")
    assert fs.scan_ids() == {"scan-b"}
    with pytest.raises(FileIntegrityError):
        fs.read("scan-a", "original", meta)
