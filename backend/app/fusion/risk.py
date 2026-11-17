"""Re-identification risk score (FR-14, ADR-0015).

Question: if every direct identifier were removed, how many people could still match the
clues left in the document? Clues (quasi-identifiers) like age, gender, city and PIN each
shrink the crowd. Estimate the crowd size k as

    k = population * product(fraction of people sharing each clue)

assuming clues are independent. Small k = easy to single someone out. k < 5 is the usual
k-anonymity danger line.
"""

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

from app.detectors.types import PiiType, Span

POPULATION = 1_400_000_000  # India

# Share of the population that shares one value of each clue (documented assumptions).
FRACTION: dict[str, float] = {
    "gender": 1 / 2,
    "age_year": 1 / 80,  # exact age in years
    "age_range": 1 / 16,  # 5-year band, after generalization
    "dob": 1 / (80 * 365),  # full date of birth
    "birth_year": 1 / 80,
    "city": 1 / 5000,  # towns and cities
    "pin": 1 / 19_000,  # PIN codes
    "pin_prefix": 1 / 700,  # first 3 PIN digits (sorting district), after generalization
    "street_address": 4 / POPULATION,  # one household, ~4 people
}

DIRECT = frozenset(
    {
        PiiType.PERSON, PiiType.EMAIL, PiiType.PHONE, PiiType.AADHAAR, PiiType.PAN,
        PiiType.CARD, PiiType.GOV_ID,
    }
)  # fmt: skip

_DOB_CONTEXT = re.compile(r"\b(?:dob|born|birth|d\.o\.b)\b", re.IGNORECASE)
_PIN = re.compile(r"\d{6}")
_PIN_PREFIX = re.compile(r"\d{3}X{3}")
_AGE_RANGE = re.compile(r"\d+\s*[-–]\s*\d+")
_YEAR_ONLY = re.compile(r"(?:19|20)\d{2}")


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    DIRECT = "DIRECT"  # a direct identifier is still present


@dataclass(frozen=True)
class RiskReport:
    level: RiskLevel
    est_matches: float  # estimated crowd size k
    clues: tuple[str, ...]
    direct: tuple[str, ...] = field(default=())

    @property
    def score(self) -> float:
        """0..1, for the UI: 1 / k, capped."""
        return 1.0 if self.level is RiskLevel.DIRECT else min(1.0, 1.0 / max(self.est_matches, 1.0))


def classify(text: str, span: Span) -> str | None:
    """Map a remaining span to a clue name, or None if it is not a quasi-identifier."""
    t, v = span.pii_type, span.text
    if t is PiiType.GENDER:
        return "gender"
    if t is PiiType.AGE:
        return "age_range" if _AGE_RANGE.search(v) else "age_year"
    if t is PiiType.DATE:
        before = text[max(0, span.start - 20) : span.start]
        if not _DOB_CONTEXT.search(before):
            return None  # an appointment date is not about who you are
        return "birth_year" if _YEAR_ONLY.fullmatch(v.strip()) else "dob"
    if t is PiiType.LOCATION:
        return "city"
    if t is PiiType.ADDRESS:
        if _PIN_PREFIX.fullmatch(v.strip()):
            return "pin_prefix"
        return "pin" if _PIN.fullmatch(v.strip()) else "street_address"
    return None


def assess(text: str, remaining: list[Span]) -> RiskReport:
    """`remaining` = spans left visible in the output (kept, or generalized)."""
    direct = tuple(sorted({s.pii_type.value for s in remaining if s.pii_type in DIRECT}))
    clues = sorted({c for s in remaining if (c := classify(text, s)) is not None})
    # a full DOB already implies the birth year; do not count both
    if "dob" in clues and "birth_year" in clues:
        clues.remove("birth_year")

    log_k = math.log10(POPULATION) + sum(math.log10(FRACTION[c]) for c in clues)
    k = 10**log_k

    if direct:
        level = RiskLevel.DIRECT
    elif k < 5:
        level = RiskLevel.HIGH
    elif k < 1000:
        level = RiskLevel.MEDIUM
    else:
        level = RiskLevel.LOW
    return RiskReport(level, round(k, 2), tuple(clues), direct)
