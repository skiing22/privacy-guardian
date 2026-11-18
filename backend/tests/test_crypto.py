import dataclasses
import hashlib
import secrets

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.crypto.audit import AuditLog, InMemoryAuditStore
from app.crypto.keys import KeyConfigError, KeyRing, KeySet, Purpose, parse_keyset
from app.crypto.tokens import Pseudonymizer
from app.crypto.vault import AccessDeniedError, Vault, VaultError
from app.detectors.types import PiiType

T = PiiType
H = secrets.token_hex(32)


def ks(*kids: str) -> KeySet:
    return KeySet(tuple((k, secrets.token_bytes(32)) for k in kids))


# ---------- keys ----------


def test_keyset_parsing_and_current() -> None:
    a, b = secrets.token_hex(32), secrets.token_hex(32)
    s = parse_keyset(f"k1:{a},k2:{b}")
    assert s.current[0] == "k2" and s.get("k1") == bytes.fromhex(a)
    assert parse_keyset(a).current[0] == "k1"
    assert "k1" in repr(s) and a not in repr(s)  # key bytes never printed


def test_bad_keys_rejected() -> None:
    with pytest.raises(KeyConfigError, match="bytes"):
        parse_keyset("abcd")  # too short
    env = {
        "PG_TOKEN_KEY": H,
        "PG_AUDIT_KEY": H,
        "PG_VAULT_KEY": secrets.token_hex(32),
        "PG_STORAGE_KEY": secrets.token_hex(32),
    }
    with pytest.raises(KeyConfigError, match="two purposes"):
        KeyRing.from_env(env)
    with pytest.raises(KeyConfigError, match="missing"):
        KeyRing.from_env({})


# ---------- HMAC tokens ----------


def test_token_is_stable_normalized_and_typed() -> None:
    p = Pseudonymizer(ks("k1"))
    a = p.token(T.PHONE, "98470 12345")
    assert a == p.token(T.PHONE, "+91 9847012345") == p.token(T.PHONE, "09847012345")
    assert a.startswith("PHONE_") and len(a) == len("PHONE_") + 6
    assert p.token(T.PERSON, "Kochi")[7:] != p.token(T.LOCATION, "Kochi")[9:]


def test_token_depends_on_key_and_is_not_a_plain_hash() -> None:
    v = "9847012345"
    t1, t2 = Pseudonymizer(ks("a")).token(T.PHONE, v), Pseudonymizer(ks("a")).token(T.PHONE, v)
    assert t1 != t2  # different secret key -> unrelated token
    plain = hashlib.sha256(b"PHONE\x00" + v.encode()).hexdigest()[:6]
    assert t1 != f"PHONE_{plain}"  # an attacker hashing all 10^10 numbers learns nothing


def test_collisions_get_longer_tokens() -> None:
    p = Pseudonymizer(ks("k1"), min_hex=1)  # 16 possible tokens: clashes are certain
    values = [f"98470{i:05d}" for i in range(200)]
    toks = [p.token(T.PHONE, v) for v in values]
    assert len(set(toks)) == len(values)  # never two values on one token
    assert p.collisions > 0 and max(len(t) for t in toks) > len("PHONE_") + 1
    assert [p.token(T.PHONE, v) for v in values] == toks  # still deterministic


@settings(max_examples=40)
@given(st.lists(st.text(min_size=1, max_size=12), min_size=1, max_size=60))
def test_tokens_are_injective(values: list[str]) -> None:
    p = Pseudonymizer(ks("k1"), min_hex=2)
    norm: dict[str, str] = {}
    for v in values:
        tok = p.token(T.EMAIL, v)
        key = v.strip().lower()
        assert norm.setdefault(tok, key) == key  # one token never covers two values


# ---------- vault ----------


def make_vault() -> tuple[Vault, AuditLog]:
    audit = AuditLog(ks("a1"))
    return Vault(ks("v1"), audit), audit


def test_vault_round_trip_is_logged() -> None:
    v, audit = make_vault()
    v.put("PHONE_abc123", T.PHONE, "98470 12345")
    assert v.reidentify("PHONE_abc123", "alice", "admin", "court order 2026/77") == "98470 12345"
    last = audit.store.all()[-1]
    assert last.event == "reidentify" and last.actor == "alice"
    assert "98470" not in str(last.payload)  # the log never holds the value (NFR-04)


def test_vault_access_rules() -> None:
    v, audit = make_vault()
    v.put("PERSON_aaaaaa", T.PERSON, "Rahul Sharma")
    with pytest.raises(AccessDeniedError):
        v.reidentify("PERSON_aaaaaa", "bob", "user", "just curious about it")
    assert audit.store.all()[-1].event == "reidentify_denied"  # attempts are logged too
    with pytest.raises(AccessDeniedError, match="reason"):
        v.reidentify("PERSON_aaaaaa", "alice", "admin", "why")
    with pytest.raises(VaultError, match="unknown"):
        v.reidentify("PERSON_ffffff", "alice", "admin", "court order 2026/77")


def test_ciphertext_cannot_be_moved_to_another_token() -> None:
    v, _ = make_vault()
    v.put("PERSON_aaaaaa", T.PERSON, "Rahul Sharma")
    v.put("PERSON_bbbbbb", T.PERSON, "Priya Iyer")
    store = v.store.data  # type: ignore[attr-defined]
    a = store["PERSON_aaaaaa"]
    store["PERSON_bbbbbb"] = dataclasses.replace(a, token="PERSON_bbbbbb")  # swap rows
    with pytest.raises(VaultError, match="integrity"):
        v.reidentify("PERSON_bbbbbb", "alice", "admin", "court order 2026/77")


def test_vault_put_is_idempotent_and_survives_rotation() -> None:
    audit = AuditLog(ks("a1"))
    old = ks("v1")
    v = Vault(old, audit)
    v.put("EMAIL_123456", T.EMAIL, "a@b.com")
    v.put("EMAIL_123456", T.EMAIL, "a@b.com")
    new = KeySet((*old.keys, ("v2", secrets.token_bytes(32))))  # rotate: add v2
    v2 = Vault(new, audit, v.store)
    assert v2.reidentify("EMAIL_123456", "alice", "admin", "court order 2026/77") == "a@b.com"


# ---------- audit chain ----------


def make_log(n: int = 5) -> AuditLog:
    log = AuditLog(ks("a1"), clock=lambda: "2026-11-18T00:00:00.000+00:00")
    for i in range(n):
        log.append("system", "scan_completed", {"scan": f"s{i}", "risk": "LOW"})
    return log


def test_clean_chain_verifies() -> None:
    log = make_log()
    assert log.verify(log.anchor()) == log.verify() and log.verify().ok


@pytest.mark.parametrize(
    ("attack", "reason"),
    [
        ("edit_payload", "payload changed"),
        ("edit_payload_and_hash", "mac mismatch"),
        ("delete", "sequence gap"),
        ("swap", "sequence gap"),
    ],
)
def test_tampering_is_detected(attack: str, reason: str) -> None:
    log = make_log()
    recs: list = log.store.records  # type: ignore[attr-defined]
    r = recs[2]
    if attack == "edit_payload":
        recs[2] = dataclasses.replace(r, payload={"scan": "s2", "risk": "HIGH"})
    elif attack == "edit_payload_and_hash":
        p = {"scan": "s2", "risk": "HIGH"}
        from app.crypto.audit import canonical

        recs[2] = dataclasses.replace(
            r, payload=p, payload_hash=hashlib.sha256(canonical(p)).hexdigest()
        )
    elif attack == "delete":
        del recs[2]
    else:
        recs[1], recs[2] = recs[2], recs[1]
    res = log.verify()
    assert not res.ok and reason in res.reason
    assert res.first_bad_seq in (1, 2)


def test_key_thief_can_rebuild_chain_but_anchor_catches_it() -> None:
    log = make_log()
    anchor = log.anchor()
    # attacker with K2 rebuilds the log without record 2, re-signing everything
    forged = AuditLog(log.keys, clock=lambda: "2026-11-18T00:00:00.000+00:00")
    for r in log.store.all():
        if r.seq != 2:
            forged.append(r.actor, r.event, r.payload)
    assert forged.verify().ok  # the honest limit of a symmetric-key chain
    assert not forged.verify(anchor).ok  # the external anchor exposes it


def test_truncation_caught_by_anchor() -> None:
    log = make_log()
    anchor = log.anchor()
    log.store.records.pop()  # type: ignore[attr-defined]
    assert log.verify().ok
    assert "truncated" in log.verify(anchor).reason


def test_chain_verifies_across_key_rotation() -> None:
    k1 = ks("a1")
    store = InMemoryAuditStore()
    AuditLog(k1, store).append("system", "x", {"n": 1})
    rotated = KeySet((*k1.keys, ("a2", secrets.token_bytes(32))))
    log = AuditLog(rotated, store)
    log.append("system", "x", {"n": 2})
    assert [r.kid for r in store.all()] == ["a1", "a2"]
    assert log.verify().ok


def test_dev_keyring_has_separate_keys() -> None:
    ring = KeyRing.dev()
    keys = {ring[p].current[1] for p in Purpose}
    assert len(keys) == 4  # token, audit, vault, storage (ADR-0022 D15)
