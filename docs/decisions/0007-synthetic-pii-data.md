# ADR-0007: Synthetic Indian PII data for training and tests

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-05, FR-06, FR-07, NFR-01

## Context
Public PII datasets have little Indian PII (Aadhaar, PAN, IFSC). Real data cannot be used.

## Decision
Write a generator that makes valid-looking values (passing Verhoeff for Aadhaar, Luhn for cards, correct PAN/IFSC format) inside realistic templates (resumes, bank letters, medical notes), with labels. Mix with a public English PII dataset for names/locations.

## Consequences
- Test set must include hand-written examples too, so we do not just learn our own templates.
- No real personal data ever enters the repo.
