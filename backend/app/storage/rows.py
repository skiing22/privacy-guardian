"""Plain row objects returned by repositories (never ORM objects; AGENTS.md 13.1)."""

import json
from dataclasses import dataclass
from typing import Any

from app.storage.files import StoredFile


@dataclass(frozen=True)
class UserRow:
    id: int
    email: str
    password_hash: str
    role: str
    is_active: bool
    created_at: str


@dataclass(frozen=True)
class ScanRow:
    id: str
    owner_id: int
    filename: str
    format: str
    status: str
    step: int
    round: int
    risk_level: str | None
    est_matches: float | None
    risk_clues: list[str] | None
    unresolved_leaks: int
    model_version: str | None
    error_code: str | None
    created_at: str
    updated_at: str
    finished_at: str | None
    expires_at: str

    @classmethod
    def from_row(cls, r: Any) -> "ScanRow":
        m = r._mapping
        clues = json.loads(m["risk_clues"]) if m["risk_clues"] is not None else None
        return cls(**{**dict(m), "risk_clues": clues})


@dataclass(frozen=True)
class FileRow:
    scan_id: str
    kind: str
    content_type: str
    size_bytes: int
    key_id: str
    nonce: bytes

    @property
    def stored(self) -> StoredFile:
        return StoredFile(self.key_id, self.nonce, self.size_bytes)


@dataclass(frozen=True)
class DecisionRow:
    scan_id: str
    idx: int
    round: int
    start_offset: int
    end_offset: int
    pii_type: str
    score: float
    sources: str
    action: str
    reason: str
    token: str | None


SCAN_COLUMNS = (
    "id, owner_id, filename, format, status, step, round, risk_level, est_matches, "
    "risk_clues, unresolved_leaks, model_version, error_code, created_at, updated_at, "
    "finished_at, expires_at"
)
DECISION_COLUMNS = (
    "scan_id, idx, round, start_offset, end_offset, pii_type, score, sources, action, reason, token"
)
