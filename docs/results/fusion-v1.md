# Fusion v1 results (M2 part 1)

Set: `data/eval/handwritten_v1.txt` (32 texts, 63 gold spans), strict exact span match. ADR-0013.
NER outputs cached in `data/eval/ner_cache_v1.jsonl`, so fusion can be re-scored without the model:
`python ml/scripts/eval_handwritten.py --ner-cache data/eval/ner_cache_v1.jsonl --show-errors`

| System | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Rules only | 1.000 | 0.286 | 0.444 |
| NER only | 0.592 | 0.714 | 0.647 |
| Greedy baseline | 0.711 | 0.857 | 0.777 |
| **Fusion v1** | **0.969** | **0.984** | **0.976** |

All rows include the phone-regex fix below (before it: baseline 0.763, fusion 0.961).

## Remaining errors
- (fixed) `09447012345` missed: **bug in rules**, not fusion. The phone regex's "no digit before" check blocked numbers with a leading 0. Fixed in `rules.py`, regression test added.
- `1800-425-3800` flagged as PHONE: a toll-free business number. Not personal; to be handled by policy (M2 utility step), not detection.
- "Mangala Lakshadweep" (a train name) flagged as LOCATION: NER error; low priority.
- "Neha Kapoor" missed after a UPI ID: NER error.

## Caveat
Fusion rules were designed while looking at v1 errors, so 0.961 is optimistic. A held-out `handwritten_v2`, written without seeing fusion output, is needed before quoting a final number.
