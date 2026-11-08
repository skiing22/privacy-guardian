# ADR-0008: Hosting target

- Status: Open
- Date: 2026-11-08
- Requirements: NFR-02, NFR-10

## Context
CPU only, free/student tier, NER model ~250 MB, needs Postgres.

## Options
1. Hugging Face Spaces (Docker) - generous RAM for the model; sleeps when idle.
2. Render - simple, but free RAM may be too small for the model.
3. Own VM (e.g. student cloud credits) - full control, more setup.
Frontend on Vercel in all cases.

## Decision
To decide at M7, after measuring real memory use in M1.
