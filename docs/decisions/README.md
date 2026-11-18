# Decision log

One file per decision (ADR). Never delete an ADR; if a decision changes, add a new ADR and mark the old one "Superseded by ADR-xxxx".

| ADR | Decision | Status | Date |
| --- | --- | --- | --- |
| [0001](0001-langgraph-state-graph.md) | LangGraph state graph, not a fixed chain | Accepted | 2026-11-08 |
| [0002](0002-hmac-pseudonyms-and-vault.md) | HMAC-SHA256 pseudonyms + AES-GCM vault | Accepted, built in 0020 | 2026-11-08 |
| [0003](0003-audit-hash-chain.md) | HMAC hash-chained audit log, with external anchor; signed reports demoted | Accepted, built in 0020 | 2026-11-08 |
| [0004](0004-beta-sensitivity-beliefs.md) | Beta distribution for sensitivity beliefs | Accepted, refined by 0016 | 2026-11-08 |
| [0005](0005-llm-optional-local.md) | LLM optional, local by default, never sees raw PII | Accepted | 2026-11-08 |
| [0006](0006-stack.md) | FastAPI + React + PostgreSQL, Docker Compose | Accepted, DB superseded for MVP by 0021 | 2026-11-08 |
| [0007](0007-synthetic-pii-data.md) | Synthetic Indian PII data for training and tests | Accepted | 2026-11-08 |
| [0008](0008-hosting.md) | Hosting target | Decided in 0022 (D13) | 2026-11-08 |
| [0009](0009-ner-dataset.md) | NER data: ai4privacy open-pii-masking-500k (English) | Accepted | 2026-11-09 |
| [0010](0010-label-mapping.md) | ai4privacy labels to PiiType, merge split names/addresses | Accepted | 2026-11-09 |
| [0011](0011-ner-model.md) | NER model: distilbert-base-cased on Colab, span-level metric | Accepted | 2026-11-09 |
| [0012](0012-handwritten-eval-set.md) | Hand-written Indian eval set; rules+NER baseline | Accepted | 2026-11-09 |
| [0013](0013-fusion.md) | Source-aware fusion: rules beat model, context words, address merge, noisy-OR | Accepted | 2026-11-18 |
| [0014](0014-entity-linking.md) | Entity linking: normalize + union-find, no link when ambiguous | Accepted | 2026-11-18 |
| [0015](0015-reid-risk.md) | Re-identification risk as estimated crowd size k | Accepted | 2026-11-18 |
| [0016](0016-two-beliefs-and-decay.md) | Two Betas per type (sensitivity + precision), cautious estimate, decay | Accepted | 2026-11-18 |
| [0017](0017-utility-policy.md) | Utility policy per span + document risk loop | Accepted | 2026-11-18 |
| [0018](0018-graph-design.md) | Graph: parallel detectors, review interrupt, stricter verifier loop, checkpoints | Accepted | 2026-11-18 |
| [0019](0019-parsers-and-chunking.md) | Parsers with offset maps; overlapping chunks with edge repair | Accepted | 2026-11-18 |
| [0020](0020-crypto-layer.md) | Crypto as built: HMAC tokens + collision check, AES-GCM vault with AAD, audit chain + anchor | Accepted | 2026-11-18 |
| [0021](0021-prd-scope-decisions.md) | MVP scope and design: SQLite, polling, PDF->txt, 6 screens + S0/S7/S8, vault 7 days, eval set v2 | Accepted | 2026-11-19 |
| [0022](0022-architecture-decisions.md) | VM hosting, session cookies, 4th storage key, model in HF repo, single worker | Accepted | 2026-11-19 |
| [0023](0023-backend-implementation-choices.md) | Backend as built: SQL DDL + Core, strict encrypted checkpoints, output rebuilt from decisions, DOCX headers emptied | Proposed | 2026-11-19 |

Template: [template.md](template.md)
