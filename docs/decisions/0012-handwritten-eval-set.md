# ADR-0012: Hand-written Indian evaluation set

- Status: Accepted
- Date: 2026-11-09
- Requirements: NFR-01

## Context
NER v1 scores 0.978 span F1 on ai4privacy validation rows, but those come from the same synthetic generator as training. We need an honest number on realistic Indian text, and a fixed baseline for M2 fusion to beat.

## Decision
- `data/eval/handwritten_v1.txt`: 32 short Indian-style texts (bank SMS, resumes, hospital notes, chats) with 64 gold spans, written in `[[value|TYPE]]` markup so it is easy to edit. Includes 7 negatives (OTPs, order numbers, train numbers, versions) to catch false positives.
- All values are fake; Aadhaar numbers pass Verhoeff and cards pass Luhn so rules can be tested.
- Scored three ways: rules only, NER only, rules+NER with a greedy baseline combiner (`app/fusion/baseline.py`). Strict exact span match.
- AADHAAR and PAN are compared as GOV_ID, since NER only knows the coarse type.
- This set is for testing only: never train on it.

## Consequences
- 64 spans is small: one error moves F1 by ~1.5 points. Report counts with the scores.
- Known gaps it exposes: landline numbers (rules only cover mobiles); UPI IDs have no type yet.
- M2 fusion (FR-11) must beat the rules+NER baseline on this set.

## Results
Baseline rules+NER F1 0.763 (P 0.697, R 0.841); see `docs/results/handwritten-v1.md`.
