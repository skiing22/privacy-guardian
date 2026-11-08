"""NER detector (FR-07): wraps our fine-tuned DistilBERT (ADR-0011).

transformers/torch are imported lazily, so the rest of the backend (and CI) does not need
them. Tests inject a fake `pipe`.
"""

from collections.abc import Callable
from typing import Any

from app.detectors.types import PiiType, Span

SOURCE = "ner"

# Words the model sometimes pulls into a name ("Patient Arjun Nair"). Trimmed off the front.
ROLE_WORDS = frozenset(
    {"patient", "dr", "mr", "mrs", "ms", "miss", "prof", "shri", "smt", "sri", "kumari"}
)

NerPipe = Callable[[str], list[dict[str, Any]]]


def load_pipeline(model_path: str) -> NerPipe:
    from transformers import pipeline  # type: ignore[import-not-found, unused-ignore]

    pipe: NerPipe = pipeline(
        "token-classification",
        model=model_path,
        tokenizer=model_path,
        aggregation_strategy="first",
    )
    return pipe


def _trim(text: str, start: int, end: int, pii_type: PiiType) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if pii_type is PiiType.PERSON:
        while True:
            word_end = start
            while word_end < end and not text[word_end].isspace():
                word_end += 1
            word = text[start:word_end].rstrip(".").lower()
            if word in ROLE_WORDS and word_end < end:
                start = word_end
                while start < end and text[start].isspace():
                    start += 1
            else:
                break
    return start, end


class NerDetector:
    def __init__(
        self, model_path: str | None = None, threshold: float = 0.5, pipe: NerPipe | None = None
    ) -> None:
        if pipe is None and model_path is None:
            raise ValueError("give model_path or pipe")
        self._model_path = model_path
        self._pipe = pipe
        self.threshold = threshold

    @property
    def pipe(self) -> NerPipe:
        if self._pipe is None:
            assert self._model_path is not None
            self._pipe = load_pipeline(self._model_path)
        return self._pipe

    def detect(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for ent in self.pipe(text):
            score = float(ent["score"])
            try:
                pii_type = PiiType(ent["entity_group"])
            except ValueError:
                continue  # label we do not use
            if score < self.threshold:
                continue
            start, end = _trim(text, int(ent["start"]), int(ent["end"]), pii_type)
            if start >= end:
                continue
            spans.append(Span(start, end, text[start:end], pii_type, round(score, 4), SOURCE))
        return sorted(spans, key=lambda s: (s.start, s.end))
