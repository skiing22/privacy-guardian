# ADR-0019: File parsers with offset maps; overlapping chunks with edge repair

- Status: Accepted
- Date: 2026-11-18
- Requirements: FR-01, FR-02, FR-03, FR-04

## Context
Users upload TXT, PDF, DOCX and CSV. Detection works on one plain string, but results must point back to the original layout (page, paragraph, row/column). DistilBERT reads at most 512 tokens, so long documents would be cut off silently.

## Decision
`backend/app/parsers/`:
- **Libraries:** pypdf (pure Python, text layer only) and python-docx. No OCR (scanned PDFs are out of scope; the parser says so instead of returning empty text). Max 10 MB.
- **Offset map (FR-02):** each parser joins pieces into one text and records `Segment(start, end, loc)` per piece ("page 2", "table 1 r1c2", "row 3, col mobile"). `locate(offset)` is a binary search.
- **CSV:** every cell becomes `header: value`, so the header gives the detectors context ("mobile: 9847012345").
- **CSV columns (FR-04):** sample up to 50 rows; a column is type T if T is found in at least 50% of its non-empty cells. Lets a user protect a whole column at once.
- **Chunking (FR-03):** windows of ~1,500 characters (under 512 tokens) with 200 characters of overlap, cut at spaces. `ChunkedDetector` wraps any detector:
  - spans touching an inner cut edge may be cut in half, so they are dropped; the overlap guarantees the neighbouring window holds them whole (for entities shorter than the overlap);
  - the same span found in two windows is kept once, highest score.
  A property test places a name at 60 random positions in a long text and checks it is found exactly once with the right offset.
- **Demo CLI:** `python -m app.cli scan FILE` runs the full graph with the real model, asks review questions in the terminal, and saves beliefs to `data/beliefs.json` (git-ignored) so learning carries across runs (FR-17).

## Consequences
- Character-based chunk size is an approximation of tokens; very dense text (long IDs, URLs) could still pass 512 tokens. Safer later: measure tokens with the tokenizer.
- Writing the cleaned result back into the same file format (FR-30) is M5; the offset map is what makes it possible.
