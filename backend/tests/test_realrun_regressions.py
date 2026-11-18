"""Bugs found by the first real-model run of the CLI (data/samples/patient_note.txt)."""

import re

from app.detectors.types import PiiType, Span
from app.fusion.fuse import fuse
from app.fusion.risk import RiskLevel
from app.graph.build import GraphDeps, build_graph, filter_known, result_of, start_scan
from app.policy.actions import Action
from app.policy.utility import PolicyConfig, decide

T = PiiType


class Fixed:
    def __init__(self, hits: list[tuple[str, PiiType, float]]) -> None:
        self.hits = hits

    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), w, t, sc, "ner")
            for w, t, sc in self.hits
            for m in re.finditer(re.escape(w), text)
        ]


def test_pieces_of_a_generalized_value_are_not_leaks() -> None:
    # bug: "30-34" came back as "[REDACTED]-[REDACTED]" after 3 rounds
    t = "age 30-34. DOB 1992."
    spans = [Span(4, 6, "30", T.AGE, 0.9, "ner"), Span(7, 9, "34", T.AGE, 0.9, "ner")]
    assert filter_known(t, spans, ["30-34", "1992"]) == []


def test_generalized_age_survives_the_graph() -> None:
    ner = Fixed([("34", T.AGE, 0.9), ("30", T.AGE, 0.9), ("Arjun Nair", T.PERSON, 0.95)])
    res = result_of(
        start_scan(build_graph(GraphDeps(detectors={"ner": ner})), "Arjun Nair, age 34.", "r1")
    )
    assert res.output == "PERSON_1, age 30-34."
    assert res.rounds == 1


def test_span_never_crosses_a_line_break() -> None:
    # bug: "Kozhikode\nPatient" ate the word Patient and merged two lines
    t = "Sunrise Hospital, Kozhikode\nPatient: Arjun"
    i = t.index("Kozhikode")
    out = fuse(t, [Span(i, i + 17, t[i : i + 17], T.LOCATION, 0.9, "ner")])
    assert [s.text for s in out] == ["Kozhikode"]


def test_business_number_not_overruled_by_risk_loop() -> None:
    # bug: toll-free number was kept as "business number", then masked by the risk loop
    t = "Mr. Nair may call 1800-425-3800 for queries."
    span = Span(18, 31, "1800-425-3800", T.PHONE, 0.95, "rules")
    res = decide(t, [span], lambda _t: 0.0, PolicyConfig())
    assert res.decisions[0].action is Action.KEEP
    assert res.risk.level is RiskLevel.LOW
    assert "1800-425-3800" in res.output


def test_final_risk_covers_whole_document_not_last_round() -> None:
    # bug: after a second round, risk said "clues: none" though "Male" was visible
    ner = Fixed([("Anil", T.PERSON, 0.4)])  # missed in round 1, caught by the verifier
    from app.detectors.context import ContextDetector

    deps = GraphDeps(detectors={"ner": ner, "context": ContextDetector()}, review_threshold=0.0)
    res = result_of(start_scan(build_graph(deps), "Ask Anil, male, today", "r2"))
    assert res.rounds == 2
    assert "gender" in res.risk.clues
