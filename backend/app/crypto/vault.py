"""AES-GCM vault: token -> original value, for admin re-identification only (FR-25, FR-33).

HMAC tokens are one-way, so getting a value back needs a separate encrypted store.
- AES-256-GCM, random 96-bit nonce per entry (never reused with the same key).
- Associated data = token | type | key id. GCM authenticates it, so a ciphertext copied
  onto another token's row fails to decrypt (no swapping rows in the database).
- Re-identify needs role "admin" AND a written reason, and is always audit-logged
  BEFORE the value is returned (if logging fails, nothing is revealed).
"""

import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.audit import AuditLog
from app.crypto.keys import KeySet
from app.detectors.types import PiiType

NONCE_BYTES = 12
MIN_REASON = 10


class VaultError(Exception):
    pass


class AccessDeniedError(VaultError):
    pass


@dataclass(frozen=True)
class VaultEntry:
    token: str
    pii_type: str
    kid: str
    nonce: bytes
    ciphertext: bytes


class VaultStore(Protocol):
    def get(self, token: str) -> VaultEntry | None: ...
    def put(self, entry: VaultEntry) -> None: ...


class InMemoryVaultStore:
    def __init__(self) -> None:
        self.data: dict[str, VaultEntry] = {}

    def get(self, token: str) -> VaultEntry | None:
        return self.data.get(token)

    def put(self, entry: VaultEntry) -> None:
        self.data[entry.token] = entry


def _aad(token: str, pii_type: str, kid: str) -> bytes:
    return f"{token}|{pii_type}|{kid}".encode()


class Vault:
    def __init__(self, keys: KeySet, audit: AuditLog, store: VaultStore | None = None) -> None:
        self.keys, self.audit = keys, audit
        self.store: VaultStore = store or InMemoryVaultStore()

    def put(self, token: str, t: PiiType, value: str) -> None:
        if self.store.get(token) is not None:
            return  # idempotent: graph nodes may re-run on resume
        kid, key = self.keys.current
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(key).encrypt(nonce, value.encode(), _aad(token, t.value, kid))
        self.store.put(VaultEntry(token, t.value, kid, nonce, ct))

    def _decrypt(self, e: VaultEntry) -> str:
        try:
            key = self.keys.get(e.kid)
            pt = AESGCM(key).decrypt(e.nonce, e.ciphertext, _aad(e.token, e.pii_type, e.kid))
        except (InvalidTag, ValueError) as err:
            raise VaultError(f"vault entry for {e.token} failed integrity check") from err
        return pt.decode()

    def reidentify(self, token: str, actor: str, role: str, reason: str) -> str:
        if role != "admin":
            self.audit.append(actor, "reidentify_denied", {"token": token, "role": role})
            raise AccessDeniedError("only admins can re-identify")
        if len(reason.strip()) < MIN_REASON:
            raise AccessDeniedError(f"a reason of at least {MIN_REASON} characters is required")
        entry = self.store.get(token)
        if entry is None:
            raise VaultError(f"unknown token {token}")
        value = self._decrypt(entry)  # verify integrity before logging success
        self.audit.append(actor, "reidentify", {"token": token, "reason": reason.strip()})
        return value
