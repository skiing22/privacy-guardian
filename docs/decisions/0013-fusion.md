# ADR-0013: Source-aware span fusion

- Status: Accepted
- Date: 2026-11-18
- Requirements: FR-08, FR-11, FR-12

## Context
M1 baseline (greedy: highest score wins) scored F1 0.763 on the hand-written set. Main errors: model guesses beating validated rules, harmless numbers flagged (OTP, order, room), split Indian addresses, keyword words tagged ("Aadhaar").

## Options
1. Keep greedy, tune thresholds - cannot fix "model beats checksum" or split addresses.
2. Learned combiner (e.g. logistic regression on features) - needs more labelled data than 63 spans.
3. Rule-based fusion pipeline with clear, testable steps.

## Decision
Option 3, in `backend/app/fusion/fuse.py`:
1. **Clean:** trim spaces/`,;:-`; drop keyword words ("Aadhaar", "PAN") and masked values (`XX4521`).
2. **Context (FR-08):** for model-found numbers, words in the 24 chars before change the score: OTP/order/room/train/version/ending x0.2; mobile/call/age x1.1. Rules spans are not touched (already validated).
3. **Threshold** 0.5.
4. **Resolve (FR-11):** overlapping spans form clusters (interval sweep, O(n log n)). Inside a cluster, rank by source priority (rules > context > NER), then score, then length. Rules win because a checksum is stronger evidence than a model score.
5. **Calibrate (FR-12):** winner's score = noisy-OR of all overlapping spans of the same type family: 1 - prod(1 - s_i). Two weak agreeing sources give a strong result.
6. **Relabel:** a lone capitalised word tagged ADDRESS ("Bhopal") becomes LOCATION.
7. **Merge** (repeat until stable): ADDRESS pieces join; LOCATION joins ADDRESS if it has a street word ("Green Park") or only a space between ("Nehru Nagar"); a 6-digit PIN never joins a city; split GOV_ID/PERSON join across one space.
8. **Expand:** a weekday before a DATE joins it.

New `ContextDetector` finds gender words (male/female) that NER missed.

## Consequences
- Every step is a pure function with its own test; tests are built from real M1 errors.
- **Overfitting risk:** these rules were designed while looking at the v1 test errors, so the v1 score after fusion is optimistic. A new held-out set (`handwritten_v2`), written without looking at fusion output, is needed before quoting a final number.
- Keyword lists are English and India-focused; they need review for other text styles.
