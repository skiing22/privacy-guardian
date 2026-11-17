"""Canonical form of a PII value, so the same thing written two ways compares equal.

Used by entity linking (FR-13) and, in M4, by HMAC pseudonyms (FR-24, ADR-0002):
"98470 12345" and "+91 9847012345" must give the same token.
"""

import re

from app.detectors.types import PiiType

TITLES = frozenset(
    {"mr", "mrs", "ms", "miss", "dr", "prof", "shri", "smt", "sri", "kumari", "patient"}
)


def name_tokens(value: str) -> list[str]:
    """Lowercase name parts without titles or dots: "Dr. R. Sharma" -> ["r", "sharma"]."""
    words = re.findall(r"[^\W\d_]+", value.lower())
    return [w for w in words if w not in TITLES]


def normalize(value: str, pii_type: PiiType) -> str:
    v = value.strip()
    if pii_type is PiiType.PHONE:
        d = re.sub(r"\D", "", v)
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        elif len(d) == 11 and d.startswith("0"):
            d = d[1:]
        return d
    if pii_type in (PiiType.AADHAAR, PiiType.CARD):
        return re.sub(r"\D", "", v)
    if pii_type in (PiiType.PAN, PiiType.IFSC, PiiType.GOV_ID):
        return re.sub(r"[\s-]", "", v).upper()
    if pii_type is PiiType.EMAIL:
        return v.lower()
    if pii_type is PiiType.PERSON:
        return " ".join(name_tokens(v))
    return re.sub(r"\s+", " ", v).lower()
