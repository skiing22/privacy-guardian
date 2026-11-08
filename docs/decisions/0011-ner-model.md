# ADR-0011: NER model - distilbert-base-cased, trained on Colab

- Status: Accepted
- Date: 2026-11-09
- Requirements: FR-07, NFR-01, NFR-02

## Context
We need a token-classification model that runs on CPU at deploy time (< 5 s per page) and trains on free hardware.

## Options
1. bert-base-cased - stronger, but ~110M params; slower on CPU.
2. distilbert-base-cased - ~66M params, about 60% faster than BERT, small accuracy loss.
3. spaCy small model - very fast, but weaker on PII types like IDs and emails.

## Decision
Option 2, cased (capital letters are a strong signal for names). Train on Google Colab T4: 50k English rows, 2 epochs, lr 5e-5, max length 256. Only the first sub-token of each word is labelled.
The headline metric is exact span match (start, end and type all correct), not token-level F1, since token F1 looks better than what users actually see.
Code: `ml/train_ner.ipynb`, helpers in `backend/app/detectors/ner_labels.py` (unit-tested).

## Consequences
- Weights (~260 MB) live in Google Drive, not git.
- Training data has few Indian names: check with hand-written Indian samples; may need fine-tuning on the synthetic generator data later.

## Results
Span-level F1 0.978 on 5,000 validation rows; see `docs/results/ner-v1.md`.
