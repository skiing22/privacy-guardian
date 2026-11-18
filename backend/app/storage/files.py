"""Encrypted file store for uploads and cleaned outputs (DATABASE 3.4, ADR-0022 D15).

Path is derived, never stored: DATA_DIR/files/{scan_id}.{kind}. AES-256-GCM with the
storage key; associated data = scan_id|kind|key_id, so a file copied onto another scan
or kind fails to decrypt.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.crypto.keys import KeySet

NONCE_BYTES = 12


class FileIntegrityError(Exception):
    pass


@dataclass(frozen=True)
class StoredFile:
    key_id: str
    nonce: bytes
    size_bytes: int


def _aad(scan_id: str, kind: str, kid: str) -> bytes:
    return f"{scan_id}|{kind}|{kid}".encode()


class EncryptedFileStore:
    def __init__(self, root: Path, keys: KeySet) -> None:
        self.root = root
        self.keys = keys
        root.mkdir(parents=True, exist_ok=True)

    def path(self, scan_id: str, kind: str) -> Path:
        return self.root / f"{scan_id}.{kind}"

    def write(self, scan_id: str, kind: str, data: bytes) -> StoredFile:
        kid, key = self.keys.current
        nonce = os.urandom(NONCE_BYTES)
        ct = AESGCM(key).encrypt(nonce, data, _aad(scan_id, kind, kid))
        tmp = self.path(scan_id, kind).with_suffix(".tmp")
        tmp.write_bytes(ct)
        tmp.replace(self.path(scan_id, kind))  # atomic: never a half-written file
        return StoredFile(kid, nonce, len(data))

    def read(self, scan_id: str, kind: str, meta: StoredFile) -> bytes:
        try:
            ct = self.path(scan_id, kind).read_bytes()
            key = self.keys.get(meta.key_id)
            return AESGCM(key).decrypt(meta.nonce, ct, _aad(scan_id, kind, meta.key_id))
        except (InvalidTag, FileNotFoundError, ValueError) as e:
            raise FileIntegrityError(f"file {kind} of scan failed integrity check") from e

    def delete_scan(self, scan_id: str) -> None:
        for p in self.root.glob(f"{scan_id}.*"):
            p.unlink(missing_ok=True)

    def scan_ids(self, min_age_s: float = 0.0) -> set[str]:
        """Scan ids that have files; `min_age_s` skips files written in the last seconds."""
        cutoff = time.time() - min_age_s
        return {
            p.name.split(".", 1)[0]
            for p in self.root.iterdir()
            if p.is_file() and p.stat().st_mtime <= cutoff
        }
