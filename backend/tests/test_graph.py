"""Graph behaviour with fake NER (no model needed in CI)."""

import re

from langgraph.checkpoint.memory import InMemorySaver

from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType, Span
from app.graph.build import (
    GraphDeps,
    build_graph,
    filter_known,
    pending_review,
    result_of,
    resume_scan,
    start_scan,
)
from app.graph.serde import make_serde

T = PiiType


class FakeNer:
    """Returns fixed (word, type, score) hits wherever the word appears."""

    def __init__(self, hits: list[tuple[str, PiiType, float]]) -> None:
        self.hits = hits

    def detect(self, text: str) -> list[Span]:
        out = []
        for word, t, score in self.hits:
            for m in re.finditer(re.escape(word), text):
                out.append(Span(m.start(), m.end(), word, t, score, "ner"))
        return out


def deps(hits: list[tuple[str, PiiType, float]], **kw: object) -> GraphDeps:
    dets = {"rules": RuleDetector(), "ner": FakeNer(hits), "context": ContextDetector()}
    return GraphDeps(detectors=dets, **kw)  # type: ignore[arg-type]


def test_detectors_run_in_parallel_then_fan_in() -> None:
    app = build_graph(deps([]))
    edges = {(e.source, e.target) for e in app.get_graph().edges}
    for d in ("detect_rules", "detect_ner", "detect_context"):
        assert ("__start__", d) in edges and (d, "fuse") in edges
    res = result_of(start_scan(app, "call 9847012345", "t1"))
    round0 = [e.node for e in res.events if e.round == 0]
    assert set(round0[:3]) == {"detect_rules", "detect_ner", "detect_context"}
    assert round0[3] == "fuse"


def test_clean_scan_one_round() -> None:
    app = build_graph(deps([("Rahul Sharma", T.PERSON, 0.95)]))
    state = start_scan(app, "Rahul Sharma: call 98470 12345", "t2")
    assert pending_review(state) is None
    res = result_of(state)
    assert res.output == "PERSON_1: call PHONE_1"
    assert res.rounds == 1 and res.unresolved_leaks == ()


def test_low_confidence_pauses_for_review_and_learns() -> None:
    d = deps([("Kochi", T.LOCATION, 0.6)])
    app = build_graph(d)
    state = start_scan(app, "Meet me in Kochi", "t3", org="acme")
    items = pending_review(state)
    assert items is not None and items[0]["text"] == "Kochi"
    assert items[0]["reason"] == "low confidence"

    p_before = d.learner.store.get("acme", T.LOCATION).precision.mean
    res = result_of(resume_scan(app, "t3", [{"index": 0, "verdict": "not_pii"}]))
    assert res.output == "Meet me in Kochi"  # reviewer said it is not PII
    assert d.learner.store.get("acme", T.LOCATION).precision.mean < p_before


def test_reviewer_keep_is_respected() -> None:
    app = build_graph(deps([("Priya", T.PERSON, 0.6)]))
    start_scan(app, "Thanks Priya", "t4")
    res = result_of(resume_scan(app, "t4", [{"index": 0, "verdict": "keep"}]))
    assert res.output == "Thanks Priya"


def test_resume_after_restart() -> None:
    """FR-23: a new graph object (as after a server restart) continues the paused scan."""
    saver = InMemorySaver(serde=make_serde())  # SQLite file in production (test_checkpoints.py)
    app1 = build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver)
    assert pending_review(start_scan(app1, "Thanks Priya", "t5")) is not None
    del app1

    app2 = build_graph(deps([("Priya", T.PERSON, 0.6)]), checkpointer=saver)
    res = result_of(resume_scan(app2, "t5", [{"index": 0, "verdict": "protect"}]))
    assert res.output == "Thanks PERSON_1"


def test_verifier_catches_a_miss_and_loops() -> None:
    # 0.4: below the first-pass threshold (0.5), above the verifier's (0.35)
    app = build_graph(deps([("Anil", T.PERSON, 0.4)], review_threshold=0.0))
    res = result_of(start_scan(app, "Ask Anil today", "t6"))
    assert res.rounds == 2
    assert res.output == "Ask PERSON_1 today"
    assert res.unresolved_leaks == ()
    assert res.history[1].decisions[0].reason == "review"  # forced protect in round 2


class FirstWord:
    """A paranoid detector: always flags the first plain word. Never satisfied."""

    def detect(self, text: str) -> list[Span]:
        for m in re.finditer(r"\b[a-z]+\b", text):
            return [Span(m.start(), m.end(), m.group(), T.PERSON, 0.4, "ner")]
        return []


def test_loop_stops_at_max_rounds() -> None:
    d = GraphDeps(detectors={"x": FirstWord()}, review_threshold=0.0, max_rounds=3)
    res = result_of(start_scan(build_graph(d), "alpha beta gamma delta epsilon", "t7"))
    assert res.rounds == 3
    assert len(res.unresolved_leaks) == 1  # reported, not hidden


def test_filter_known_ignores_our_own_output() -> None:
    t = "PERSON_1 at [REDACTED], 98*** ***45, age 30-34"
    spans = [
        Span(0, 8, "PERSON_1", T.PERSON, 0.9, "ner"),
        Span(12, 22, "[REDACTED]", T.ADDRESS, 0.9, "ner"),
        Span(24, 35, "98*** ***45", T.PHONE, 0.9, "ner"),
        Span(41, 46, "30-34", T.AGE, 0.9, "ner"),
    ]
    assert filter_known(t, spans, ["30-34"]) == []
