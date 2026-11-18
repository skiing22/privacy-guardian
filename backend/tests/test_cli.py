import re
from typing import Any

from app.cli import print_result, scan
from app.detectors.context import ContextDetector
from app.detectors.rules import RuleDetector
from app.detectors.types import PiiType, Span
from app.parsers.files import parse_file
from app.policy.beliefs import BeliefLearner, InMemoryBeliefStore


class FakeNer:
    def detect(self, text: str) -> list[Span]:
        out = []
        for word, t, sc in [("Arjun Nair", PiiType.PERSON, 0.95), ("Kochi", PiiType.LOCATION, 0.6)]:
            for m in re.finditer(word, text):
                out.append(Span(m.start(), m.end(), word, t, sc, "ner"))
        return out


def dets() -> dict[str, Any]:
    return {"rules": RuleDetector(), "ner": FakeNer(), "context": ContextDetector()}


def test_cli_scan_with_review_and_learning(capsys: Any) -> None:
    doc = parse_file("../data/samples/patient_note.txt")
    store = InMemoryBeliefStore()
    learner = BeliefLearner(store)
    asked: list[str] = []

    def ask(item: dict[str, Any]) -> dict[str, Any]:
        asked.append(item["text"])
        return {"index": item["index"], "verdict": "keep"}

    res = scan(doc.text, dets(), learner, "demo", ask)
    assert asked == ["Kochi"]
    assert "Arjun Nair" not in res.output and "98470" not in res.output
    assert "Kochi" in res.output  # reviewer said keep
    assert "1800-425-3800" in res.output  # business number kept
    assert store.get("demo", PiiType.LOCATION).sensitivity.mean < 0.4  # learned

    print_result(res, doc.locate)
    out = capsys.readouterr().out
    assert "cleaned output" in out and "line 2" in out


def test_cli_auto_mode_never_asks() -> None:
    doc = parse_file("../data/samples/employees.csv")
    res = scan(doc.text, dets(), BeliefLearner(InMemoryBeliefStore()), "demo", None)
    assert "9847012345" not in res.output


def test_columns_use_fused_detection_not_ner_alone() -> None:
    # bug from the real run: NER alone called the mobile column GOV_ID
    from pathlib import Path

    from app.cli import fused_detector
    from app.parsers.files import classify_columns

    class WrongNer:
        def detect(self, text: str) -> list[Span]:
            m = re.search(r"\d{10}", text)
            return [Span(m.start(), m.end(), m.group(), PiiType.GOV_ID, 0.99, "ner")] if m else []

    detect = fused_detector({"rules": RuleDetector(), "ner": WrongNer()})
    data = Path("../data/samples/employees.csv").read_bytes()
    verdicts = {v.column: v.pii_type for v in classify_columns(data, detect)}
    assert verdicts["mobile"] is PiiType.PHONE  # validated rule beats the model guess
