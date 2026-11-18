import re

from app.crypto.keys import KeyRing
from app.crypto.services import CryptoServices
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType, Span
from app.graph.build import GraphDeps, build_graph, result_of, resume_scan, start_scan


class FakeNer:
    def __init__(self, hits: list[tuple[str, PiiType, float]]) -> None:
        self.hits = hits

    def detect(self, text: str) -> list[Span]:
        return [
            Span(m.start(), m.end(), w, t, sc, "ner")
            for w, t, sc in self.hits
            for m in re.finditer(re.escape(w), text)
        ]


HITS = [("Rahul Sharma", PiiType.PERSON, 0.95), ("Rahul", PiiType.PERSON, 0.95)]


def graph(crypto: CryptoServices, hits: list[tuple[str, PiiType, float]] = HITS):  # type: ignore[no-untyped-def]
    d = GraphDeps(detectors={"rules": RuleDetector(), "ner": FakeNer(hits)}, crypto=crypto)
    return build_graph(d)


def test_hmac_tokens_are_stable_across_documents() -> None:
    c = CryptoServices.build(KeyRing.dev())
    app = graph(c)
    a = result_of(start_scan(app, "Rahul Sharma: 98470 12345", "d1")).output
    b = result_of(start_scan(app, "Call +91 9847012345. Rahul says hi.", "d2")).output
    pa, pb = re.findall(r"PHONE_[0-9a-f]+", a), re.findall(r"PHONE_[0-9a-f]+", b)
    assert pa == pb and len(pa) == 1  # same phone, two docs, written differently
    assert re.fullmatch(r"PERSON_[0-9a-f]{6}: PHONE_[0-9a-f]{6}", a)


def test_vault_and_audit_after_scan() -> None:
    c = CryptoServices.build(KeyRing.dev(), actor="tester")
    out = result_of(start_scan(graph(c), "Rahul Sharma called. Rahul left.", "d3")).output
    tok = re.findall(r"PERSON_[0-9a-f]+", out)
    assert len(set(tok)) == 1 and len(tok) == 2  # both mentions, one token
    assert c.vault.reidentify(tok[0], "admin1", "admin", "fraud investigation 42") == "Rahul Sharma"
    events = [r.event for r in c.audit.store.all()]
    assert events == ["scan_completed", "reidentify"]
    assert c.audit.verify().ok
    dump = str([r.payload for r in c.audit.store.all()])
    assert "Rahul" not in dump  # no raw PII in the audit log


def test_review_is_audited_once_even_though_node_reruns() -> None:
    c = CryptoServices.build(KeyRing.dev())
    app = graph(c, [("Priya", PiiType.PERSON, 0.6)])
    start_scan(app, "Thanks Priya", "d4")
    result_of(resume_scan(app, "d4", [{"index": 0, "verdict": "protect"}]))
    events = [r.event for r in c.audit.store.all()]
    assert events == ["review", "scan_completed"]
    assert "Priya" not in str(c.audit.store.all()[0].payload)
