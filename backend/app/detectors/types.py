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
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORG = "ORG"
    DATE = "DATE"


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
