"""HMAC pseudonyms (FR-24, ADR-0002).

token = TYPE_ + first n hex of HMAC-SHA256(K1, TYPE || 0x00 || normalize(value))

- Same value -> same token, in every document (joinable data), after normalization:
  "98470 12345" and "+91 9847012345" give the same PHONE token.
- The type is inside the HMAC input (domain separation): "Kochi" as PERSON and as
  LOCATION give unrelated tokens.
- Without K1 nobody can recompute a token, so a token cannot be brute-forced back to a
  phone number (only 10^10 options: a plain hash would fall in minutes).
- Collisions: n=6 hex is 24 bits, so two different values clash with ~50% chance after
  ~4,800 values of one type (birthday bound). The registry stores the full MAC of every
  issued token; on a clash the new value gets a longer token. Deterministic and checked.
"""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol

from app.crypto.keys import KeySet
from app.detectors.types import PiiType
from app.fusion.normalize import normalize

MIN_HEX = 6
MAX_HEX = 64


@dataclass(frozen=True)
class TokenEntry:
    full_mac: str  # hex; identifies the value without revealing it
    kid: str


class TokenRegistry(Protocol):
    def get(self, token: str) -> TokenEntry | None: ...
    def put(self, token: str, entry: TokenEntry) -> None: ...


class InMemoryTokenRegistry:
    def __init__(self) -> None:
        self.data: dict[str, TokenEntry] = {}

    def get(self, token: str) -> TokenEntry | None:
        return self.data.get(token)

    def put(self, token: str, entry: TokenEntry) -> None:
        self.data[token] = entry


class Pseudonymizer:
    def __init__(
        self, keys: KeySet, registry: TokenRegistry | None = None, min_hex: int = MIN_HEX
    ) -> None:
        if not 1 <= min_hex <= MAX_HEX:
            raise ValueError("min_hex out of range")
        self.keys = keys
        self.registry: TokenRegistry = registry or InMemoryTokenRegistry()
        self.min_hex = min_hex
        self.collisions = 0

    def mac(self, t: PiiType, value: str) -> str:
        _, key = self.keys.current
        msg = t.value.encode() + b"\x00" + normalize(value, t).encode()
        return hmac.new(key, msg, hashlib.sha256).hexdigest()

    def token(self, t: PiiType, value: str) -> str:
        full = self.mac(t, value)
        kid, _ = self.keys.current
        for n in range(self.min_hex, MAX_HEX + 1):
            tok = f"{t.value}_{full[:n]}"
            seen = self.registry.get(tok)
            if seen is None:
                self.registry.put(tok, TokenEntry(full, kid))
                return tok
            if hmac.compare_digest(seen.full_mac, full):
                return tok  # same value seen before
            self.collisions += 1  # different value already owns this prefix: go longer
        raise RuntimeError("unreachable: full 256-bit MAC collision")
