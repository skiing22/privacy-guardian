# ADR-0024: One address item from street to city; PIN apart; no label words in values

- Status: Accepted
- Date: 2026-11-26
- Requirements: FR-11, FR-12, NFR-01
- Changes: the merge rule in ADR-0013 step 7 ("a city stays apart")

## Context
Held-out set v2 scored F1 0.795 (`docs/results/handwritten-v2.md`). 20 of its 33 errors were
about where an address ends. v1 labels and the code split `14 MG Road, Kochi` into ADDRESS +
LOCATION; the v2 labels, checked by the owner, keep it as one ADDRESS. Neither rule was written
down, so both sets were "right". The split also left `, ` visible between the two tokens, and
two real bugs showed up: "Green Park Apartments" cut after "Park" (the word `Apartments` stayed
in the cleaned file) and `PIN 452016` kept the word PIN.

## Options
1. Keep the split, relabel v2. Tokens keep the city as a separate, coarser LOCATION. But the
   reader still sees the address's shape, and v2 is the held-out set, so it must not be relabelled.
2. One ADDRESS from street to city; city alone stays LOCATION; PIN always apart. Hides the whole
   address behind one token; matches the owner-checked v2 labels.

## Decision
Option 2, plus two fixes:
- A city right after a street part (gap: a comma and/or one or two spaces, no full stop) joins it.
- A 6-digit PIN is never merged into another item.
- A following building word (`Apartments`, `Road`, `Colony`, … from `STREET_WORDS`) is pulled
  into an address the model cut short.
- A leading label word (`PIN`, `OTP`, `PAN`, … from `STOPWORDS`) is trimmed off a value, so
  context rules can also see it.

v1 labels were updated to this rule (3 lines); v2 labels already follow it.

## Consequences
- v1 F1 stays at the same level (0.976 → 0.975). v2 rises from 0.795 to 0.922, **but v2 has now
  been used to find this fix**, so 0.795 stays the held-out number until a new set v3 is scored.
- A company or person name that is a label word ("Pan Singh") would lose that word. Not seen in
  any set; watch for it in v3.
