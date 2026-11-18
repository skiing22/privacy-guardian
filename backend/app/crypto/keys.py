"""Secret keys, one set per purpose, each with a key id for rotation (FR-29, ADR-0002).

Three purposes, three independent keys, so one leaked key does not break everything:
  token -> HMAC pseudonyms (K1)     audit -> audit hash chain (K2)     vault -> AES-GCM (K3)

Env format (newest key LAST, older keys kept so old data can still be checked/decrypted):
  PG_TOKEN_KEY=k1:<64 hex chars>,k2:<64 hex chars>
A bare hex string means a single key with id "k1".
Generate a key:  python -c "import secrets; print(secrets.token_hex(32))"
"""

import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

MIN_KEY_BYTES = 32


class Purpose(StrEnum):
    TOKEN = "token"
    AUDIT = "audit"
    VAULT = "vault"


ENV_NAMES = {
    Purpose.TOKEN: "PG_TOKEN_KEY",
    Purpose.AUDIT: "PG_AUDIT_KEY",
    Purpose.VAULT: "PG_VAULT_KEY",
}


class KeyConfigError(ValueError):
    pass


@dataclass(frozen=True)
class KeySet:
    keys: tuple[tuple[str, bytes], ...]  # (kid, key), oldest first

    def __post_init__(self) -> None:
        if not self.keys:
            raise KeyConfigError("empty key set")
        kids = [k for k, _ in self.keys]
        if len(set(kids)) != len(kids):
            raise KeyConfigError("duplicate key id")
        for kid, key in self.keys:
            if len(key) < MIN_KEY_BYTES:
                raise KeyConfigError(f"key {kid} is {len(key)} bytes; need >= {MIN_KEY_BYTES}")

    @property
    def current(self) -> tuple[str, bytes]:
        return self.keys[-1]

    def get(self, kid: str) -> bytes:
        for k, key in self.keys:
            if k == kid:
                return key
        raise KeyConfigError(f"unknown key id {kid!r}")

    def __repr__(self) -> str:  # never print key bytes into logs
        return f"KeySet(kids={[k for k, _ in self.keys]})"


def parse_keyset(raw: str) -> KeySet:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out: list[tuple[str, bytes]] = []
    for i, p in enumerate(parts, 1):
        kid, _, hexkey = p.rpartition(":")
        try:
            key = bytes.fromhex(hexkey)
        except ValueError as e:
            raise KeyConfigError("key must be hex") from e
        out.append((kid or f"k{i}", key))
    return KeySet(tuple(out))


@dataclass(frozen=True)
class KeyRing:
    sets: Mapping[Purpose, KeySet]

    def __getitem__(self, p: Purpose) -> KeySet:
        return self.sets[p]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "KeyRing":
        env = os.environ if env is None else env
        missing = [n for n in ENV_NAMES.values() if not env.get(n)]
        if missing:
            raise KeyConfigError(f"missing keys: {', '.join(missing)} (see .env.example)")
        sets = {p: parse_keyset(env[n]) for p, n in ENV_NAMES.items()}
        raws = [k for s in sets.values() for _, k in s.keys]
        if len(set(raws)) != len(raws):
            raise KeyConfigError("the same key is used for two purposes; use separate keys")
        return cls(sets)

    @classmethod
    def dev(cls, seed: str = "privacy-guardian-dev") -> "KeyRing":
        """DEV/TEST ONLY: fixed keys derived from a seed, so demo runs are repeatable."""

        def derive(p: Purpose) -> bytes:
            return hmac.new(seed.encode(), f"dev-key:{p.value}".encode(), hashlib.sha256).digest()

        return cls({p: KeySet((("dev1", derive(p)),)) for p in Purpose})
