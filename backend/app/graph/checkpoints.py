"""Encrypted, durable graph checkpoints (ARCHITECTURE 4.4, ADR-0022 D15).

Checkpoints hold the document text, so every blob is sealed with AES-256-GCM under the
storage key (PG_STORAGE_KEY). The cipher name carries the key id ("aesgcm:<kid>"), so
old checkpoints stay readable after a key rotation.

LangGraph's EncryptedSerializer falls back to plain data when a row has no cipher name.
We refuse that: a row planted on disk without encryption must never be loaded.
"""

import os
import sqlite3
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from langgraph.checkpoint.serde.base import CipherProtocol
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from app.crypto.keys import KeySet
from app.graph.serde import make_serde

NONCE_BYTES = 12
PREFIX = "aesgcm:"


class CheckpointIntegrityError(Exception):
    pass


class AesGcmCipher(CipherProtocol):
    def __init__(self, keys: KeySet) -> None:
        self.keys = keys

    def encrypt(self, plaintext: bytes) -> tuple[str, bytes]:
        kid, key = self.keys.current
        nonce = os.urandom(NONCE_BYTES)
        return PREFIX + kid, nonce + AESGCM(key).encrypt(nonce, plaintext, kid.encode())

    def decrypt(self, ciphername: str, ciphertext: bytes) -> bytes:
        if not ciphername.startswith(PREFIX):
            raise CheckpointIntegrityError("unknown checkpoint cipher")
        kid = ciphername[len(PREFIX) :]
        try:
            key = self.keys.get(kid)
            nonce, body = ciphertext[:NONCE_BYTES], ciphertext[NONCE_BYTES:]
            return AESGCM(key).decrypt(nonce, body, kid.encode())
        except (InvalidTag, ValueError, KeyError) as e:
            raise CheckpointIntegrityError("checkpoint failed integrity check") from e


class StrictEncryptedSerializer(EncryptedSerializer):
    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        if "+" not in data[0]:
            raise CheckpointIntegrityError("unencrypted checkpoint refused")
        return super().loads_typed(data)


def make_encrypted_serde(keys: KeySet) -> StrictEncryptedSerializer:
    return StrictEncryptedSerializer(AesGcmCipher(keys), serde=make_serde())


def open_checkpointer(path: Path, keys: KeySet) -> SqliteSaver:
    """SQLite checkpointer in its own file (DATA_DIR/checkpoints.db), WAL mode.
    The caller owns `saver.conn` and closes it on shutdown."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA secure_delete=ON")
    saver = SqliteSaver(conn, serde=make_encrypted_serde(keys))
    saver.setup()
    return saver
