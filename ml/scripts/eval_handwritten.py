"""Score detectors and fusion on the hand-written Indian gold set (ADR-0012, ADR-0013).

Usage (from repo root, venv active, model in ml/models/ner-distilbert-v1):
    python ml/scripts/eval_handwritten.py --show-errors
    python ml/scripts/eval_handwritten.py --save-ner data/eval/ner_cache_v1.jsonl
    python ml/scripts/eval_handwritten.py --ner-cache data/eval/ner_cache_v1.jsonl  # no model
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.detectors.context import ContextDetector  # noqa: E402
from app.detectors.ner_labels import span_scores  # noqa: E402
from app.detectors.rules import RuleDetector  # noqa: E402
from app.detectors.types import PiiType, Span  # noqa: E402
from app.eval.goldset import load  # noqa: E402
from app.fusion.baseline import greedy_resolve  # noqa: E402
from app.fusion.fuse import fuse  # noqa: E402

# NER only knows "some government ID"; compare at that level.
COARSE = {"AADHAAR": "GOV_ID", "PAN": "GOV_ID"}
Key = tuple[int, int, str]


def key(s: Span) -> Key:
    t = s.pii_type.value
    return (s.start, s.end, COARSE.get(t, t))


def table(name: str, scores: dict[str, dict[str, float]]) -> None:
    print(f"\n== {name}")
    print(f"{'type':<11}{'P':>7}{'R':>7}{'F1':>7}{'n':>5}")
    for t, m in scores.items():
        print(
            f"{t:<11}{m['precision']:7.3f}{m['recall']:7.3f}{m['f1']:7.3f}{int(m['support']):5d}"
        )


def ner_spans(texts: list[str], args: argparse.Namespace) -> list[list[Span]]:
    if args.ner_cache:
        rows = [
            json.loads(ln)
            for ln in Path(args.ner_cache).read_text("utf-8").splitlines()
        ]
        if [r["text"] for r in rows] != texts:
            sys.exit("NER cache does not match the gold set; re-run with --save-ner")
        return [
            [
                Span(s, e, r["text"][s:e], PiiType(t), sc, "ner")
                for s, e, t, sc in r["spans"]
            ]
            for r in rows
        ]
    from app.detectors.ner import NerDetector

    det = NerDetector(args.model, threshold=0.0)  # fusion applies its own threshold
    out = [det.detect(t) for t in texts]
    if args.save_ner:
        with Path(args.save_ner).open("w", encoding="utf-8") as f:
            for t, spans in zip(texts, out, strict=True):
                rows = [[s.start, s.end, s.pii_type.value, s.score] for s in spans]
                f.write(
                    json.dumps({"text": t, "spans": rows}, ensure_ascii=False) + "\n"
                )
        print("saved NER outputs to", args.save_ner)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=str(ROOT / "data/eval/handwritten_v1.txt"))
    ap.add_argument("--model", default=str(ROOT / "ml/models/ner-distilbert-v1"))
    ap.add_argument("--save-ner", help="write NER outputs to this JSONL file")
    ap.add_argument(
        "--ner-cache", help="read NER outputs from this JSONL instead of the model"
    )
    ap.add_argument("--show-errors", action="store_true")
    args = ap.parse_args()

    examples = load(Path(args.gold))
    texts = [ex.text for ex in examples]
    gold = [{(s, e, COARSE.get(t, t)) for s, e, t in ex.spans} for ex in examples]
    rules, ctx = RuleDetector(), ContextDetector()
    ner_all = ner_spans(texts, args)

    runs: dict[str, list[set[Key]]] = {
        "rules": [],
        "ner": [],
        "baseline": [],
        "fusion": [],
    }
    for t, n in zip(texts, ner_all, strict=True):
        r = rules.detect(t)
        n_kept = [s for s in n if s.score >= 0.5]
        runs["rules"].append({key(s) for s in r})
        runs["ner"].append({key(s) for s in n_kept})
        runs["baseline"].append({key(s) for s in greedy_resolve(r + n_kept)})
        runs["fusion"].append({key(s) for s in fuse(t, r + n + ctx.detect(t))})

    print(f"{len(examples)} examples, {sum(len(g) for g in gold)} gold spans")
    for name, pred in runs.items():
        table(name, span_scores(gold, pred))

    if args.show_errors:
        print("\n== fusion errors")
        for t, g, p in zip(texts, gold, runs["fusion"], strict=True):
            missed, extra = g - p, p - g
            if missed or extra:
                print(f"\n{t}")
                for s, e, typ in sorted(missed):
                    print(f"   MISSED {typ:<10} {t[s:e]!r}")
                for s, e, typ in sorted(extra):
                    print(f"   EXTRA  {typ:<10} {t[s:e]!r}")


if __name__ == "__main__":
    main()
