"""Score rules, NER, and rules+NER on the hand-written Indian gold set (ADR-0012).

Usage (from repo root, venv active, model in ml/models/ner-distilbert-v1):
    python ml/scripts/eval_handwritten.py
    python ml/scripts/eval_handwritten.py --show-errors
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.detectors.ner import NerDetector  # noqa: E402
from app.detectors.ner_labels import span_scores  # noqa: E402
from app.detectors.rules import RuleDetector  # noqa: E402
from app.detectors.types import Span  # noqa: E402
from app.eval.goldset import load  # noqa: E402
from app.fusion.baseline import greedy_resolve  # noqa: E402

# NER only knows "some government ID"; compare at that level so it is not punished
# for not knowing the specific Indian ID type.
COARSE = {"AADHAAR": "GOV_ID", "PAN": "GOV_ID"}


def key(s: Span) -> tuple[int, int, str]:
    t = s.pii_type.value
    return (s.start, s.end, COARSE.get(t, t))


def table(name: str, scores: dict[str, dict[str, float]]) -> None:
    print(f"\n== {name}")
    print(f"{'type':<11}{'P':>7}{'R':>7}{'F1':>7}{'n':>5}")
    for t, m in scores.items():
        print(f"{t:<11}{m['precision']:7.3f}{m['recall']:7.3f}{m['f1']:7.3f}{int(m['support']):5d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(ROOT / "data/eval/handwritten_v1.txt"))
    ap.add_argument("--model", default=str(ROOT / "ml/models/ner-distilbert-v1"))
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()

    examples = load(Path(args.gold))
    rules, ner = RuleDetector(), NerDetector(args.model)
    gold = [{(s, e, COARSE.get(t, t)) for s, e, t in ex.spans} for ex in examples]

    runs: dict[str, list[set[tuple[int, int, str]]]] = {"rules": [], "ner": [], "rules+ner": []}
    for ex in examples:
        r, n = rules.detect(ex.text), ner.detect(ex.text)
        runs["rules"].append({key(s) for s in r})
        runs["ner"].append({key(s) for s in n})
        runs["rules+ner"].append({key(s) for s in greedy_resolve(r + n)})

    print(f"{len(examples)} examples, {sum(len(g) for g in gold)} gold spans")
    for name, pred in runs.items():
        table(name, span_scores(gold, pred))

    if args.show_errors:
        print("\n== rules+ner errors")
        for ex, g, p in zip(examples, gold, runs["rules+ner"], strict=True):
            missed, extra = g - p, p - g
            if missed or extra:
                print(f"\n{ex.text}")
                for s, e, t in sorted(missed):
                    print(f"   MISSED {t:<10} {ex.text[s:e]!r}")
                for s, e, t in sorted(extra):
                    print(f"   EXTRA  {t:<10} {ex.text[s:e]!r}")


if __name__ == "__main__":
    main()
