# ADR-0017: Utility policy with a document-level risk loop

- Status: Accepted
- Date: 2026-11-18
- Requirements: FR-18, FR-19, FR-20

## Context
Each found span needs an action: keep, generalize, mask, pseudonymize or redact. Redacting everything is safe but destroys usefulness; keeping too much leaks identity, often through a combination of harmless-looking clues (ADR-0015).

## Decision
`app/policy/actions.py`, `app/policy/utility.py`:

**Step 1, per span.** Among actions allowed for the type, pick the highest
U(a) = w_p * s * gain(a) - w_u * loss(a), with w_p = 1.0, w_u = 0.5 and s = cautious sensitivity (ADR-0016).

| Action | gain | loss | Break-even s (action beats keep) |
| --- | --- | --- | --- |
| generalize | 0.6 | 0.2 | 0.167 |
| mask | 0.7 | 0.4 | 0.286 |
| pseudonymize | 0.9 | 0.3 | 0.167 |
| redact | 1.0 | 1.0 | 0.500 |

Pseudonymize usually beats redact: it hides the value but keeps "same person" links, so the output stays useful for analysis. Generalize is allowed only where it makes sense (age -> 5-year band, date -> year, PIN -> first 3 digits).

**Overrides (FR-20)** per type win outright (e.g. Aadhaar always redact). A toll-free number (1800/1860) is kept as a business number.

**Step 2, per document (risk loop).** Compute the risk of what stays visible. While it is above `max_risk` (default MEDIUM), strengthen one span to its next stronger allowed action: direct identifiers first, then the clue with the smallest population share. Overridden spans are never touched; if an override keeps risk high, the report says so instead of hiding it. The loop is bounded (each step strengthens one span).

Pseudonyms use entity-linking ids (PERSON_1) for now, so all mentions of one person share a token. M4 replaces them with HMAC tokens (ADR-0002).

## Consequences
- Each choice is explainable: the UI can show the utility of every action and the reason (utility / override / risk / business number).
- Greedy minimal strengthening: the DOB + gender + PIN example only turns DOB into a year (risk HIGH -> MEDIUM), keeping the rest useful. Greedy is not guaranteed optimal; fine at document size.
- Gain/loss tables are hand-set; they could later be tuned from reviewer feedback.
