# ADR-0001: LangGraph state graph, not a fixed chain

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-10, FR-21, FR-22, FR-23

## Context
v1 feedback: "just agents called one after another, one episode at a time". v2 needs parallel steps, branches, loops, a human pause, and resume after crash.

## Options
1. Plain LangChain chain - simple, but strictly linear.
2. Hand-written orchestrator - full control, but we rebuild state, checkpoints and interrupts ourselves.
3. LangGraph state graph - fan-out/fan-in, conditional edges, cycles, `interrupt`, Postgres checkpointer built in.

## Decision
Option 3. LangChain only for LLM/tool wrappers inside nodes.

## Consequences
- Every node is a pure function of graph state, so each node can be unit-tested alone.
- Must cap loops (max 3 verifier rounds) to avoid infinite cycles.
- Adds a dependency that changes fast; pin the version.
