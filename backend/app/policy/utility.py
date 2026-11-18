"""Utility policy (FR-18 to FR-20, ADR-0017).

Step 1, per span: pick the allowed action with the highest utility
    U(a) = w_p * s * gain(a) - w_u * loss(a)
where s = cautious sensitivity of the type (beliefs, ADR-0016).
An admin override for the type (FR-20) wins outright.

Step 2, per document: compute re-identification risk (ADR-0015) of what is left visible.
While it is worse than allowed, strengthen one span: direct identifiers first, then the
most identifying clue (smallest population share). Overridden spans are never changed.
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from app.detectors.types import PiiType, Span
from app.fusion.linking import link
from app.fusion.risk import DIRECT, FRACTION, RiskLevel, RiskReport, assess, classify
from app.policy.actions import (
    PRIVACY_GAIN,
    USEFULNESS_LOSS,
    Action,
    allowed,
    generalize,
    render,
)

_TOLL_FREE = re.compile(r"\s*1[- ]?8[06]0[\d\s-]*")
_LEVEL_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.DIRECT]


@dataclass(frozen=True)
class PolicyConfig:
    w_privacy: float = 1.0
    w_usefulness: float = 0.5
    max_risk: RiskLevel = RiskLevel.MEDIUM  # strengthen until risk <= this
    overrides: dict[PiiType, Action] = field(default_factory=dict)  # FR-20


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str  # "utility", "override", "review", "risk", "business number", "leak"
    utilities: dict[Action, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PolicyResult:
    decisions: list[Decision]
    risk: RiskReport
    output: str
    tokens: dict[int, str]  # span index -> pseudonym


def utility(a: Action, s: float, cfg: PolicyConfig) -> float:
    return round(cfg.w_privacy * s * PRIVACY_GAIN[a] - cfg.w_usefulness * USEFULNESS_LOSS[a], 4)


def choose(span: Span, s: float, cfg: PolicyConfig) -> Decision:
    acts = allowed(span.pii_type, span.text)
    if span.pii_type in cfg.overrides:
        a = cfg.overrides[span.pii_type]
        return Decision(a if a in acts else Action.REDACT, "override")
    if span.pii_type is PiiType.PHONE and _TOLL_FREE.fullmatch(span.text):
        return Decision(Action.KEEP, "business number")
    us = {a: utility(a, s, cfg) for a in acts}
    best = max(acts, key=lambda a: (us[a], -PRIVACY_GAIN[a]))  # tie -> weaker action
    return Decision(best, "utility", us)


def visible_spans(spans: list[Span], decisions: list[Decision]) -> list[Span]:
    """What an attacker still sees: kept spans, and generalized ones in generalized form.
    Business numbers (toll-free) are not about a person, so they are not counted."""
    out = []
    for s, d in zip(spans, decisions, strict=True):
        if d.reason == "business number":
            continue
        if d.action is Action.KEEP:
            out.append(s)
        elif d.action is Action.GENERALIZE:
            out.append(replace(s, text=generalize(s.pii_type, s.text)))
    return out


def _stronger(span: Span, current: Action) -> Action | None:
    for a in allowed(span.pii_type, span.text):
        if PRIVACY_GAIN[a] > PRIVACY_GAIN[current]:
            return a
    return None


def _pick_to_strengthen(text: str, spans: list[Span], ds: list[Decision]) -> int | None:
    best: tuple[int, float] | None = None
    for i, (s, d) in enumerate(zip(spans, ds, strict=True)):
        if d.reason in ("override", "review", "business number") or d.action not in (
            Action.KEEP,
            Action.GENERALIZE,
        ):
            continue
        if _stronger(s, d.action) is None:
            continue
        vis = visible_spans([s], [d])[0]
        if s.pii_type in DIRECT and d.action is Action.KEEP:
            rank = -1.0  # direct identifiers first
        elif (c := classify(text, vis)) is not None:
            rank = FRACTION[c]  # smaller share = more identifying
        else:
            continue
        if best is None or rank < best[1]:
            best = (i, rank)
    return None if best is None else best[0]


def decide(
    text: str,
    spans: list[Span],
    sensitivity: Callable[[PiiType], float],
    cfg: PolicyConfig,
    forced: Mapping[int, Action] | None = None,
) -> PolicyResult:
    """`forced`: span index -> action chosen by a human reviewer; never changed by the loop."""
    forced = forced or {}
    ds = [
        Decision(forced[i], "review") if i in forced else choose(s, sensitivity(s.pii_type), cfg)
        for i, s in enumerate(spans)
    ]

    risk = assess(text, visible_spans(spans, ds))
    for _ in range(4 * len(spans) + 1):  # each step strengthens one span: bounded
        if _LEVEL_ORDER.index(risk.level) <= _LEVEL_ORDER.index(cfg.max_risk):
            break
        i = _pick_to_strengthen(text, spans, ds)
        if i is None:
            break  # nothing more we may change (e.g. overrides keep values visible)
        nxt = _stronger(spans[i], ds[i].action)
        assert nxt is not None
        ds[i] = Decision(nxt, "risk", ds[i].utilities)
        risk = assess(text, visible_spans(spans, ds))

    tokens = {i: e.id for e in link(spans) for i in e.mentions}
    return PolicyResult(ds, risk, apply(text, spans, ds, tokens), tokens)


def apply(text: str, spans: list[Span], ds: list[Decision], tokens: dict[int, str]) -> str:
    """Replace spans from the end so earlier offsets stay valid."""
    out = text
    for i in sorted(range(len(spans)), key=lambda k: spans[k].start, reverse=True):
        s, d = spans[i], ds[i]
        new = render(d.action, s.pii_type, s.text, tokens.get(i, f"{s.pii_type.value}_?"))
        out = out[: s.start] + new + out[s.end :]
    return out
