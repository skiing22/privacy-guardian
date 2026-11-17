"""Learned beliefs per PII type (FR-15 to FR-17, ADR-0004, ADR-0016).

Two separate Beta beliefs per type, because a review answers two different questions:
- sensitivity: "does this kind of data need protecting?"  (drives the action choice)
- precision:   "when we flag this type, is it really PII?" (drives the review threshold)
Marking a false alarm ("that's an order number, not a phone") must NOT teach the system
that phone numbers are harmless. Mixing the two signals was a v1 weakness.
"""

import json
import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.detectors.types import PiiType

PRIOR_STRENGTH = 10.0  # prior counts as 10 reviews: early feedback moves it, but not wildly

# Prior mean sensitivity per type (documented starting point, learned from there).
PRIOR_SENSITIVITY: dict[PiiType, float] = {
    PiiType.AADHAAR: 0.95, PiiType.CARD: 0.95, PiiType.PAN: 0.85, PiiType.GOV_ID: 0.85,
    PiiType.PHONE: 0.80, PiiType.EMAIL: 0.70, PiiType.PERSON: 0.70, PiiType.ADDRESS: 0.70,
    PiiType.IP_ADDRESS: 0.50, PiiType.LOCATION: 0.40, PiiType.DATE: 0.30, PiiType.AGE: 0.30,
    PiiType.IFSC: 0.30, PiiType.GENDER: 0.20, PiiType.ORG: 0.20,
}  # fmt: skip
PRIOR_PRECISION = 0.8


class Feedback(StrEnum):
    PROTECT = "protect"  # reviewer kept it masked/redacted -> more sensitive
    KEEP = "keep"  # reviewer chose to show it -> less sensitive
    NOT_PII = "not_pii"  # false alarm -> detector precision down, sensitivity untouched
    CONFIRMED = "confirmed"  # reviewer agreed it is PII -> precision up


@dataclass(frozen=True)
class Beta:
    alpha: float
    beta: float

    @classmethod
    def from_mean(cls, mean: float, strength: float = PRIOR_STRENGTH) -> "Beta":
        return cls(mean * strength, (1 - mean) * strength)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def std(self) -> float:
        a, b = self.alpha, self.beta
        return math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))

    @property
    def cautious(self) -> float:
        """mean + 1 std, capped: when unsure, assume more sensitive (privacy-safe side)."""
        return min(1.0, self.mean + self.std)

    def update(self, positive: bool, prior: "Beta", decay: float = 1.0) -> "Beta":
        """Bayesian update. `decay` < 1 fades old evidence toward the prior (forgetting)."""
        a = prior.alpha + decay * (self.alpha - prior.alpha)
        b = prior.beta + decay * (self.beta - prior.beta)
        return Beta(a + (1 if positive else 0), b + (0 if positive else 1))


@dataclass(frozen=True)
class TypeBelief:
    sensitivity: Beta
    precision: Beta


def prior(t: PiiType) -> TypeBelief:
    return TypeBelief(Beta.from_mean(PRIOR_SENSITIVITY[t]), Beta.from_mean(PRIOR_PRECISION))


class BeliefStore(Protocol):
    def get(self, org: str, t: PiiType) -> TypeBelief: ...
    def put(self, org: str, t: PiiType, b: TypeBelief) -> None: ...


class InMemoryBeliefStore:
    """Dict-backed store. The Postgres store (M5) has the same two methods."""

    def __init__(self) -> None:
        self._data: dict[tuple[str, PiiType], TypeBelief] = {}

    def get(self, org: str, t: PiiType) -> TypeBelief:
        return self._data.get((org, t), prior(t))

    def put(self, org: str, t: PiiType, b: TypeBelief) -> None:
        self._data[(org, t)] = b

    def reset(self, org: str) -> None:
        """Admin reset after bad feedback (ADR-0004)."""
        self._data = {k: v for k, v in self._data.items() if k[0] != org}

    def to_json(self) -> str:
        rows = [
            [
                o,
                t.value,
                b.sensitivity.alpha,
                b.sensitivity.beta,
                b.precision.alpha,
                b.precision.beta,
            ]
            for (o, t), b in sorted(self._data.items())
        ]
        return json.dumps(rows)

    @classmethod
    def from_json(cls, raw: str) -> "InMemoryBeliefStore":
        s = cls()
        for o, t, sa, sb, pa, pb in json.loads(raw):
            s.put(o, PiiType(t), TypeBelief(Beta(sa, sb), Beta(pa, pb)))
        return s


class BeliefLearner:
    def __init__(self, store: BeliefStore, decay: float = 1.0) -> None:
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        self.store = store
        self.decay = decay

    def record(self, org: str, t: PiiType, fb: Feedback) -> TypeBelief:
        cur, p = self.store.get(org, t), prior(t)
        if fb in (Feedback.PROTECT, Feedback.KEEP):
            new = TypeBelief(
                cur.sensitivity.update(fb is Feedback.PROTECT, p.sensitivity, self.decay),
                cur.precision.update(True, p.precision, self.decay),  # it was real PII
            )
        else:
            new = TypeBelief(
                cur.sensitivity,
                cur.precision.update(fb is Feedback.CONFIRMED, p.precision, self.decay),
            )
        self.store.put(org, t, new)
        return new

    def sensitivity(self, org: str, t: PiiType) -> float:
        return self.store.get(org, t).sensitivity.cautious
