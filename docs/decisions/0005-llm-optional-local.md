# ADR-0005: LLM optional, local by default, never sees raw PII

- Status: Accepted
- Date: 2026-11-08
- Requirements: FR-09, NFR-04

## Context
An LLM helps with hard context cases, but sending raw PII to an external API defeats the purpose of the tool.

## Decision
The LLM detector is optional and off by default. If on: local model via Ollama, or an external API that only receives text where already-found PII is masked.

## Consequences
- Core accuracy must come from rules + NER, not the LLM.
- Deploy stays CPU-only and free-tier friendly.
