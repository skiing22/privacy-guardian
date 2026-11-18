# ADR-0021: MVP scope and design decisions from PRD.md and DESIGN.md (D1-D12)

- Status: Accepted (approved by owner, 2026-11-19)
- Date: 2026-11-19
- Supersedes in part: ADR-0006 (database), SRS sections 6.1-6.2 (screens, SSE). D1 is reopened and replaced by D13 (ADR-0022)

## Context
After M4 the project was re-scoped in `docs/PRD.md` to finish a working, deployed MVP and avoid over-engineering. `docs/DESIGN.md` defines the UI, following four design skills (frontend-design, landing-page-design, design-taste-frontend, ui-ux-pro-max), with their conflicts resolved in its section 0. Where PRD/DESIGN and the older SRS disagree, PRD/DESIGN win.

## Decisions
| ID | Decision |
| --- | --- |
| D1 | (Replaced by D13) Host on Hugging Face Spaces |
| D2 | **SQLite** for MVP instead of PostgreSQL. Store interfaces stay, so Postgres is a later swap |
| D3 | One organisation per deployment |
| D4 | Output: TXT, CSV, DOCX in the same format; PDF returned as cleaned `.txt` |
| D5 | React frontend: 6 app screens (PRD section 8) |
| D6 | Progress by polling every 1 s, not Server-Sent Events |
| D7 | One combined scan page for run, review and result |
| D8 | Vault entries deleted with their document after 7 days |
| D9 | No accuracy number on resume/README until a held-out test set v2 is scored |
| D10 | Audit anchor in a local file for the demo; off-server anchor documented as the production step |
| D11 | Static Privacy and terms page (S7) and 404 page (S8), linked from every footer |
| D12 | One public landing page (S0) with a single "Try the demo" action, built last in M7; real screenshots and real figures only |

Design (DESIGN.md): Manrope + Geist Mono, blue-black ink accent (no violet), sharp radius scale, Tailwind type steps with named styles, Phosphor icons, no gradients, no scroll fade-ins in the app, one signature "redaction pass" moment.

Cut from MVP: Insights screen, developer API keys, multiple orgs, LLM detector (FR-09), signed reports (FR-28), OCR.

## Consequences
- ADR-0006's PostgreSQL choice is superseded for MVP only; ADR-0008 (hosting) is decided by D13 (ADR-0022).
- The resume accuracy claim waits for test set v2 (D9).
