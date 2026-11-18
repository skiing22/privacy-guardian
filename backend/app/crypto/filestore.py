"""File-backed stores for the CLI demo. The API (M5) uses Postgres with the same methods.

Files live in data/ (git-ignored): audit.jsonl, vault.json, tokens.json.
audit.jsonl is plain text on purpose: edit a line by hand and `audit verify` catches it.
"""

import base64
import json
from dataclasses import asdict
from pathlib import Path

from app.crypto.audit import AuditRecord
from app.crypto.tokens import TokenEntry
from app.crypto.vault import VaultEntry


class JsonlAuditStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, rec: AuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    def all(self) -> list[AuditRecord]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [AuditRecord(**json.loads(ln)) for ln in lines if ln.strip()]


class _JsonDict:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, dict[str, str]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")


class JsonVaultStore(_JsonDict):
    def get(self, token: str) -> VaultEntry | None:
        d = self.data.get(token)
        if d is None:
            return None
        return VaultEntry(
            d["token"], d["pii_type"], d["kid"],
            base64.b64decode(d["nonce"]), base64.b64decode(d["ciphertext"]),
        )  # fmt: skip

    def put(self, entry: VaultEntry) -> None:
        self.data[entry.token] = {
            "token": entry.token, "pii_type": entry.pii_type, "kid": entry.kid,
            "nonce": base64.b64encode(entry.nonce).decode(),
            "ciphertext": base64.b64encode(entry.ciphertext).decode(),
        }  # fmt: skip
        self._save()


class JsonTokenRegistry(_JsonDict):
    def get(self, token: str) -> TokenEntry | None:
        d = self.data.get(token)
        return TokenEntry(d["full_mac"], d["kid"]) if d else None

    def put(self, token: str, entry: TokenEntry) -> None:
        self.data[token] = {"full_mac": entry.full_mac, "kid": entry.kid}
        self._save()
