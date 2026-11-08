"""Shared types for all detectors."""

from dataclasses import dataclass
from enum import StrEnum


class PiiType(StrEnum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    AADHAAR = "AADHAAR"
    PAN = "PAN"
    IFSC = "IFSC"
    CARD = "CARD"
    IP_ADDRESS = "IP_ADDRESS"
    GOV_ID = "GOV_ID"  # other government IDs (passport, licence, tax, ...)
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ADDRESS = "ADDRESS"
    ORG = "ORG"  # no training data yet (ADR-0010); kept for rules/LLM
    DATE = "DATE"
    AGE = "AGE"  # quasi-identifier (FR-14)
    GENDER = "GENDER"  # quasi-identifier (FR-14)


@dataclass(frozen=True, slots=True)
class Span:
    """One PII item found in text. `end` is exclusive, like Python slicing."""

    start: int
    end: int
    text: str
    pii_type: PiiType
    score: float
    source: str

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end:
            raise ValueError(f"bad span offsets: {self.start}..{self.end}")
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score out of range: {self.score}")
