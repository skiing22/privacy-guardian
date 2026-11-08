# ADR-0003: HMAC hash-chained audit log; signed reports demoted

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-26, FR-27, FR-28

## Context
We want to prove the audit log was not edited (who scanned what, who re-identified whom).

## Options
1. Plain table - any DB admin can edit rows silently.
2. Hash chain with SHA-256 - detects edits, but anyone can recompute the whole chain after editing.
3. Hash chain with HMAC(K2) - only a key holder can recompute it.

## Decision
Option 3: mac_i = HMAC(K2, hash(record_i) || mac_{i-1}).
Known limit: an attacker who steals K2 from the server can rewrite the whole chain. Fix: periodically copy the latest mac outside the server (e.g. a scheduled job writes it to a separate store or a git commit). Then a rewritten chain no longer matches the anchor.
Signed reports (FR-28) are demoted from Should to Could: only key holders can verify an HMAC signature, so the value to outside readers is low. A public-key signature (Ed25519) would fix that if needed later.

## Consequences
- Verify is O(n); fine at our scale.
- Records must be serialized the same way every time (canonical JSON) or verify breaks.
