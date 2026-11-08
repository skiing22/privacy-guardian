# ADR-0006: FastAPI + React + PostgreSQL, Docker Compose

- Status: Accepted
- Date: 2026-11-08
- Requirements: NFR-10

## Context
Python is needed for ML and LangGraph. We need async, SSE, typed APIs, and one-command start.

## Decision
FastAPI + Pydantic + SQLAlchemy/Alembic; PostgreSQL (also used by the LangGraph checkpointer); React + Vite + Tailwind; Docker Compose; GitHub Actions CI (ruff, mypy strict, pytest, docker build).

## Consequences
- One database for app data and graph checkpoints.
- mypy strict from day one: slower at first, fewer bugs later.
