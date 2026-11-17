"""Context detector and context scoring (FR-08).

Two jobs:
1. Find quasi-identifiers that are plain words (gender words), which NER sometimes misses.
2. Give a score factor for a model-found number from the words just before it:
   "OTP is 482913" -> not PII; "mobile 7012345678" -> PII.
"""

import re

from app.detectors.types import PiiType, Span

SOURCE = "context"
WINDOW = 24  # characters looked at before a span

_GENDER = re.compile(r"\b(?:male|female|transgender)\b", re.IGNORECASE)

NEGATIVE = frozenset(
    {
        "otp", "order", "room", "train", "platform", "version", "android", "ios", "ending",
        "invoice", "ticket", "ref", "build", "page", "chapter", "step", "flight", "seat",
    }
)  # fmt: skip
POSITIVE = frozenset(
    {"mobile", "phone", "call", "contact", "whatsapp", "aadhaar", "dob", "born", "age"}
)
NEGATIVE_FACTOR = 0.2
POSITIVE_FACTOR = 1.1

_WORD = re.compile(r"[a-z]+")


class ContextDetector:
    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), m.group(), PiiType.GENDER, 0.9, SOURCE)
            for m in _GENDER.finditer(text)
        ]


def is_numeric(s: str) -> bool:
    chars = [c for c in s if not c.isspace()]
    return bool(chars) and sum(c.isdigit() for c in chars) / len(chars) >= 0.5


def context_factor(text: str, span: Span) -> float:
    """Score multiplier from the words right before a numeric span. 1.0 = no signal."""
    if not is_numeric(span.text):
        return 1.0
    words = set(_WORD.findall(text[max(0, span.start - WINDOW) : span.start].lower()))
    if words & NEGATIVE:
        return NEGATIVE_FACTOR
    if words & POSITIVE:
        return POSITIVE_FACTOR
    return 1.0
