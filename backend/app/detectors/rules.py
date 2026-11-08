"""Rule detector (FR-05, FR-06): regex finds candidates, validators confirm them."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.detectors import validators as v
from app.detectors.types import PiiType, Span

SOURCE = "rules"
SCORE_CHECKSUM = 0.99  # passed a checksum: very unlikely to be random
SCORE_FORMAT = 0.95  # passed a strict format check only


@dataclass(frozen=True)
class Rule:
    pii_type: PiiType
    pattern: re.Pattern[str]
    validate: Callable[[str], bool]
    score: float


_NOT_DIGIT_BEFORE = r"(?<![\d])"
_NOT_DIGIT_AFTER = r"(?![\d])"

RULES: tuple[Rule, ...] = (
    Rule(
        PiiType.EMAIL,
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        lambda s: True,
        SCORE_FORMAT,
    ),
    Rule(
        PiiType.AADHAAR,
        re.compile(_NOT_DIGIT_BEFORE + r"[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}" + _NOT_DIGIT_AFTER),
        v.aadhaar_valid,
        SCORE_CHECKSUM,
    ),
    Rule(
        PiiType.CARD,
        re.compile(_NOT_DIGIT_BEFORE + r"\d(?:[ -]?\d){12,18}" + _NOT_DIGIT_AFTER),
        v.card_valid,
        SCORE_CHECKSUM,
    ),
    Rule(
        PiiType.PHONE,
        re.compile(
            r"(?:(?<![\w+])\+91[ -]?|(?<!\d)0)?"
            + _NOT_DIGIT_BEFORE
            + r"[6-9]\d{4}[ -]?\d{5}"
            + _NOT_DIGIT_AFTER
        ),
        v.indian_mobile_valid,
        SCORE_FORMAT,
    ),
    Rule(PiiType.PAN, re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), v.pan_valid, SCORE_FORMAT),
    Rule(PiiType.IFSC, re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), v.ifsc_valid, SCORE_FORMAT),
    Rule(
        PiiType.IP_ADDRESS,
        re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
        v.ipv4_valid,
        SCORE_FORMAT,
    ),
)


class RuleDetector:
    """Returns every validated candidate. Overlaps are resolved later by fusion (FR-11)."""

    def __init__(self, rules: tuple[Rule, ...] = RULES) -> None:
        self.rules = rules

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for rule in self.rules:
            for m in rule.pattern.finditer(text):
                if rule.validate(m.group()):
                    spans.append(
                        Span(m.start(), m.end(), m.group(), rule.pii_type, rule.score, SOURCE)
                    )
        return sorted(spans, key=lambda s: (s.start, s.end))
