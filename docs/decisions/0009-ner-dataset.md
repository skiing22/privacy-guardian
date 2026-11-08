# ADR-0009: NER training data - ai4privacy open-pii-masking-500k

- Status: Accepted
- Date: 2026-11-09
- Requirements: FR-07, NFR-01

## Context
We need labelled PII text to fine-tune the NER detector. Candidates were ai4privacy, CoNLL-2003, or a mix.

## Options
1. ai4privacy pii-masking-300k - large, but its license is academic/non-commercial only and forbids redistribution and derivative works without written permission.
2. ai4privacy open-pii-masking-500k - tagged CC-BY-4.0, ~580k rows, 20 PII classes, ~17% India-region rows, char-level spans given directly.
3. CoNLL-2003 - only PERSON/ORG/LOC/MISC; no IDs, emails, phones.

## Decision
Option 2, English rows only (`language == "en"`). Downloaded by `ml/scripts/fetch_ai4privacy.py` into `data/raw/` (git-ignored); never committed. Credit Ai4Privacy in the README and any report.
Rules + validators (ADR-0007 generator) still cover Aadhaar/PAN/IFSC, since checksums beat a model there.

## Consequences
- Data is synthetic and short (~17 words avg): add a small hand-written test set so scores are not inflated.
- Our PiiType set is smaller than its 20 labels: a label mapping is needed (next ADR, after seeing label counts).
- Re-check the license file before any commercial use; terms say commercial users should contact Ai4Privacy.
