"""Pure helpers for NER training and evaluation (FR-07, NFR-01).

Kept free of torch/transformers so they run in CI and are unit-tested.
"""

from collections import Counter
from collections.abc import Iterable, Sequence

from app.detectors.label_map import AI4PRIVACY_MAP, MappedSpan

IGNORE = -100  # label id the loss function skips


def build_label_list() -> list[str]:
    """BIO labels for every type the NER learns: O, B-ADDRESS, I-ADDRESS, ..."""
    types = sorted({t.value for t in AI4PRIVACY_MAP.values() if t is not None})
    return ["O"] + [f"{p}-{t}" for t in types for p in ("B", "I")]


def align_labels(
    offsets: Sequence[tuple[int, int]],
    word_ids: Sequence[int | None],
    spans: Sequence[MappedSpan],
    label2id: dict[str, int],
) -> list[int]:
    """One label per token. Only the first sub-token of each word is labelled; the rest
    and special tokens get IGNORE. A word is B- if it starts its span, else I-."""
    out: list[int] = []
    prev: int | None = None
    for wid, (s, _e) in zip(word_ids, offsets, strict=True):
        if wid is None or wid == prev:
            out.append(IGNORE)
        else:
            lab = "O"
            for a, b, t in spans:
                if a <= s < b:
                    lab = f"{'B' if s == a else 'I'}-{t.value}"
                    break
            out.append(label2id[lab])
        prev = wid
    return out


Entity = tuple[int, int, str]  # start, end, type


def span_scores(
    gold: Iterable[set[Entity]], pred: Iterable[set[Entity]]
) -> dict[str, dict[str, float]]:
    """Exact-match precision / recall / F1 per type and overall ("ALL").
    A prediction counts only if start, end and type all match."""
    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for g, p in zip(gold, pred, strict=True):
        for e in p & g:
            tp[e[2]] += 1
        for e in p - g:
            fp[e[2]] += 1
        for e in g - p:
            fn[e[2]] += 1

    def prf(t: int, f_p: int, f_n: int) -> dict[str, float]:
        prec = t / (t + f_p) if t + f_p else 0.0
        rec = t / (t + f_n) if t + f_n else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {"precision": prec, "recall": rec, "f1": f1, "support": float(t + f_n)}

    types = sorted(set(tp) | set(fp) | set(fn))
    out = {t: prf(tp[t], fp[t], fn[t]) for t in types}
    out["ALL"] = prf(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    return out
