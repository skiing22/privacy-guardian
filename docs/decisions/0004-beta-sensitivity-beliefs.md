# ADR-0004: Beta distribution for sensitivity beliefs

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-15, FR-16, FR-17

## Context
The system should learn from review feedback how sensitive each PII type is, and keep that across sessions.

## Options
1. Fixed weights - no learning.
2. Running average - learns, but no idea of how sure it is.
3. Beta(alpha, beta) per PII type - conjugate to accept/reject feedback, gives mean and uncertainty.

## Decision
Option 3. Accept -> alpha += 1, reject -> beta += 1. Sensitivity s = alpha / (alpha + beta). Priors set per type (e.g. Aadhaar starts high).

## Consequences
- Update is O(1) and easy to explain.
- Beliefs can drift from one bad reviewer; keep per-org beliefs and allow admin reset.
