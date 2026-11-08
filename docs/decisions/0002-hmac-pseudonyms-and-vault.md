# ADR-0002: HMAC-SHA256 pseudonyms + AES-GCM vault

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-24, FR-25, FR-33

## Context
Users need the same real value to get the same token across files (so data stays joinable), and admins sometimes need the real value back.

## Options
1. Random tokens - safe, but not consistent across files without a lookup table.
2. Plain SHA-256 of the value - consistent, but brute-forceable: an Indian mobile number has ~10^10 options, which a laptop can hash in minutes.
3. HMAC-SHA256 with a secret key - consistent, and cannot be brute-forced without the key.

## Decision
Option 3 for tokens: `TYPE_` + first 6 hex chars of HMAC(K1, normalize(value)). Normalize first (trim, lowercase, digits only for phones) so "98765 43210" and "9876543210" match.
Since HMAC is one-way, reversal uses a separate vault: token -> AES-GCM(K3, value). Admin-only, reason required, always logged.

## Consequences
- 6 hex = 24 bits: collisions are possible past a few thousand values of one type. Check on insert; extend length on collision.
- Losing K1 means new tokens no longer match old ones. Store a key ID with each token (FR-29).
- Separate keys for tokens and vault: one leaked key does not expose both.
