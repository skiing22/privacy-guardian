"""Baseline span combiner, used only until real fusion (FR-11, M2) exists.

Greedy: sort by score (rules win ties), keep a span if it overlaps nothing kept so far.
This gives the M1 "rules + NER" number that M2 fusion must beat.
"""

from app.detectors.types import Span


def greedy_resolve(spans: list[Span]) -> list[Span]:
    ranked = sorted(spans, key=lambda s: (-s.score, s.source != "rules", s.start))
    kept: list[Span] = []
    for s in ranked:
        if all(s.end <= k.start or s.start >= k.end for k in kept):
            kept.append(s)
    return sorted(kept, key=lambda s: s.start)
