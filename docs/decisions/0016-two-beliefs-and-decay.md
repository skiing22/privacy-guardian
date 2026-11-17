# ADR-0016: Two Beta beliefs per type (sensitivity + precision), cautious estimate, decay

- Status: Accepted
- Date: 2026-11-18
- Refines: ADR-0004
- Requirements: FR-15, FR-16, FR-17

## Context
ADR-0004 chose one Beta(alpha, beta) per PII type: accept -> alpha+1, reject -> beta+1. But a reviewer's "reject" can mean two different things:
1. "This is PII but fine to show here" (sensitivity is lower than we thought).
2. "This is not PII at all", e.g. an order number flagged as PHONE (the detector was wrong).
With one belief, every false alarm teaches the system that phone numbers are harmless.

## Decision
`app/policy/beliefs.py`:
- **Two Betas per (org, type):** `sensitivity` (does it need protecting?) and `precision` (is a flag of this type real?).
- Feedback kinds: PROTECT (sens +1 alpha, prec +1 alpha), KEEP (sens +1 beta, prec +1 alpha), NOT_PII (prec +1 beta only), CONFIRMED (prec +1 alpha only).
- **Priors** from a documented table (Aadhaar 0.95 ... gender 0.20) with strength 10, so about 10 reviews are needed to move a belief a lot.
- **Cautious estimate** for the policy: mean + 1 std, capped at 1. With little evidence we lean to "more sensitive" (privacy-safe side); the gap shrinks as reviews add up.
- **Decay** (optional, default off): before each update, evidence above the prior is multiplied by gamma < 1, so recent reviews count more and old habits fade.
- Store is a small interface (`get`, `put`); in-memory now, Postgres in M5. Per-org, with admin reset.

## Consequences
- Precision beliefs give M3 a principled review threshold: flags from a low-precision type go to human review more often.
- Cautious estimate means a new org starts slightly over-protective; that is the right failure direction for a privacy tool.
- Still vulnerable to one reviewer flooding feedback; mitigations later: per-user rate limit, or weight feedback by reviewer role.
