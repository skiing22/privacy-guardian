# ADR-0014: Entity linking with union-find and safe partial-name matching

- Status: Accepted
- Date: 2026-11-18
- Requirements: FR-13, FR-24

## Context
One document often names the same person several ways ("Rahul Sharma", "Rahul", "Mr. Sharma", "R. Sharma") and writes the same phone differently. Without linking, each mention gets a different pseudonym and the output leaks that they differ, or splits one person into many.

## Options
1. Exact text match only - misses "Rahul" vs "Rahul Sharma".
2. Embedding / coreference model - heavier, needs pronoun handling we do not need yet.
3. Normalize values, then union-find with a strict partial-name rule.

## Decision
Option 3 (`app/fusion/normalize.py`, `app/fusion/linking.py`):
- `normalize()` gives a canonical value per type (phone -> 10 digits, PAN upper case, names without titles). M4 HMAC tokens will reuse it, so linked mentions get the same token.
- Union-find joins spans with the same type + normalized value (near O(n) with path halving).
- A short name joins a full name (2+ parts, no initials) only if every short part matches a different full part (initials match by first letter) and **exactly one** full name fits. "Reddy" with both Vikram and Sneha Reddy present stays alone and is marked `ambiguous`.

## Consequences
- Prefers missing a link over a wrong link: a wrong link would give two real people one token.
- Ambiguous mentions are a natural input for human review (FR-22, M3).
- No pronouns ("he", "she") and no cross-document linking; cross-document consistency comes from HMAC tokens in M4.
