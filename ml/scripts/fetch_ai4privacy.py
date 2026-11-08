"""Download ai4privacy open-pii-masking-500k, keep English rows, save as JSONL (ADR-0009).

Usage (from repo root):
    pip install -r ml/requirements.txt
    python ml/scripts/fetch_ai4privacy.py            # all English rows
    python ml/scripts/fetch_ai4privacy.py --limit 2000   # quick sample

Output goes to data/raw/ (git-ignored). The dataset is never committed.
Prints label counts so we can decide the label mapping to our PiiType (next step).
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from datasets import load_dataset

DATASET = "ai4privacy/open-pii-masking-500k-ai4privacy"
OUT_DIR = Path("data/raw")


def parse_mask(raw: Any) -> list[dict[str, Any]]:
    """privacy_mask may arrive as a JSON string or a list, depending on the loader."""
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="max rows per split (0 = all)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ds = load_dataset(DATASET)

    for split in ds:
        print(f"{split} columns: {ds[split].column_names}")
        rows = ds[split].filter(lambda r: r["language"] == "en")
        if args.limit:
            rows = rows.select(range(min(args.limit, len(rows))))

        labels: Counter[str] = Counter()
        locales: Counter[str] = Counter()
        bad = 0
        out_path = OUT_DIR / f"ai4privacy_en_{split}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for i, r in enumerate(rows):
                text = r["source_text"]
                spans = []
                for m in parse_mask(r["privacy_mask"]):
                    start, end, label = int(m["start"]), int(m["end"]), m["label"]
                    if text[start:end] != m["value"]:  # sanity check offsets
                        bad += 1
                        continue
                    spans.append([start, end, label])
                    labels[label] += 1
                locales[r.get("locale") or "?"] += 1
                row_id = r.get("id") or r.get("uid") or f"{split}-{i}"
                rec = {"id": row_id, "locale": r.get("locale"), "text": text, "spans": spans}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"\n== {split}: {len(rows)} rows -> {out_path}  (bad offsets skipped: {bad})")
        print("locales:", dict(locales.most_common()))
        for label, n in labels.most_common():
            print(f"  {label:<20} {n}")


if __name__ == "__main__":
    main()
