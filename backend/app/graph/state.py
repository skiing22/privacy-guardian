"""Graph state (SRS section 7). Reducers decide how parallel node outputs combine."""

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from app.detectors.types import Span
from app.fusion.risk import RiskReport
from app.policy.actions import Action
from app.policy.utility import Decision


def merge_dicts(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Fan-in reducer: each detector writes its own key, so parallel writes never clash."""
    return {**a, **b}


@dataclass(frozen=True)
class ReviewItem:
    index: int
    text: str
    pii_type: str
    score: float
    reason: str  # "low confidence", "ambiguous name", "unreliable type"


@dataclass(frozen=True)
class RoundRecord:
    round: int
    text_in: str
    spans: tuple[Span, ...]
    decisions: tuple[Decision, ...]
    output: str
    risk: RiskReport
    tokens: tuple[str | None, ...] = ()  # per span: its pseudonym if pseudonymized


@dataclass(frozen=True)
class Event:
    node: str
    round: int
    ms: float
    info: str = ""


@dataclass(frozen=True)
class ScanResult:
    output: str
    risk: RiskReport
    rounds: int
    unresolved_leaks: tuple[Span, ...]
    history: tuple[RoundRecord, ...]
    events: tuple[Event, ...] = field(default=())


class GraphState(TypedDict, total=False):
    scan_id: str
    org: str
    original: str
    text: str  # text being scanned this round
    round: int
    candidates: Annotated[dict[str, list[Span]], merge_dicts]
    spans: list[Span]
    review_items: list[ReviewItem]
    forced: dict[int, Action]
    decisions: list[Decision]
    risk: RiskReport
    output: str
    allowed_values: list[str]  # values we chose to leave visible (kept / generalized)
    leaks: list[Span]
    history: Annotated[list[RoundRecord], operator.add]
    events: Annotated[list[Event], operator.add]
