# ADR-0022: Architecture decisions D13-D17

- Status: Accepted (approved by owner, 2026-11-19)
- Date: 2026-11-19
- Requirements: FR-23, FR-25, FR-32, NFR-04, NFR-05
- Details: `docs/ARCHITECTURE.md` section 18

| ID | Decision | Why |
| --- | --- | --- |
| D13 | Host on a small VM (student credits or an always-free tier, current terms checked at setup) running `docker compose` with a persistent disk. Replaces D1 | Hugging Face Spaces disks are wiped on restart, and community reports say new free Docker Spaces need a paid plan; one container + one disk is exactly this architecture |
| D14 | Server-side sessions in an `HttpOnly`, `SameSite=Strict` cookie instead of JWT | One origin; logout really revokes; no token in browser storage |
| D15 | A 4th key, `PG_STORAGE_KEY`, encrypts uploaded files and graph checkpoints at rest | Keeps one key per purpose (ADR-0002); no new dependency |
| D16 | Model weights in a private Hugging Face model repo, pinned by commit and SHA-256, downloaded at image build only | Versioned and checked; never fetched at runtime |
| D17 | One worker thread runs one scan at a time; no queue service | The model is CPU-bound; a queue service adds two moving parts for no gain at MVP scale |

## Consequences
- D13: a demo host with a temporary disk is only a fallback (seeded demo on each start).
- D14: SRS FR-32's JWT wording is superseded.
- D15: `KeyRing` gains a fourth purpose; prod refuses to start without it.
