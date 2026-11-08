from typing import Any

import pytest

from app.detectors.ner import NerDetector
from app.detectors.types import PiiType

TEXT = "Patient Arjun Nair, age 34, from Kochi 682016."


def fake_pipe(text: str) -> list[dict[str, Any]]:
    def ent(part: str, label: str, score: float) -> dict[str, Any]:
        i = text.index(part)
        return {"entity_group": label, "score": score, "start": i, "end": i + len(part)}

    return [
        ent("Patient Arjun Nair", "PERSON", 0.92),
        ent("34", "AGE", 1.0),
        ent(" Kochi", "LOCATION", 0.99),  # leading space, as pipelines sometimes return
        ent("682016", "ADDRESS", 0.3),  # below threshold
    ]


def test_trims_role_word_and_spaces_and_applies_threshold() -> None:
    spans = NerDetector(pipe=fake_pipe).detect(TEXT)
    got = [(s.text, s.pii_type) for s in spans]
    assert got == [
        ("Arjun Nair", PiiType.PERSON),
        ("34", PiiType.AGE),
        ("Kochi", PiiType.LOCATION),
    ]
    for s in spans:
        assert TEXT[s.start : s.end] == s.text
        assert s.source == "ner"


def test_role_word_alone_is_kept() -> None:
    # "Dr." with nothing after it is not trimmed to empty
    t = "Dr."
    det = NerDetector(
        pipe=lambda x: [{"entity_group": "PERSON", "score": 0.9, "start": 0, "end": 3}]
    )
    assert [s.text for s in det.detect(t)] == ["Dr."]


def test_needs_model_or_pipe() -> None:
    with pytest.raises(ValueError):
        NerDetector()
