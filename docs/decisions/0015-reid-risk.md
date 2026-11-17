# ADR-0015: Re-identification risk as estimated crowd size

- Status: Accepted
- Date: 2026-11-18
- Requirements: FR-14

## Context
Removing names is not enough. Sweeney (2000) showed ZIP code + gender + date of birth single out most of the US population. We need a per-document score of how identifiable the cleaned output still is, to warn users and to drive the policy (e.g. generalize age when risk is high).

## Options
1. Count leftover quasi-identifiers - simple, but "gender + city" and "DOB + PIN" would both score 2.
2. Real k-anonymity over a dataset - needs the whole dataset; we score single documents.
3. Estimate the crowd size k = population x product of value shares, assuming independent clues.

## Decision
Option 3 (`app/fusion/risk.py`). Shares (India, population 1.4e9): gender 1/2, exact age 1/80, 5-year age band 1/16, DOB 1/29,200, birth year 1/80, city 1/5,000, PIN 1/19,000, street address = one household (~4 people).
- DATE counts as a clue only after "DOB", "born" or "birth" (an appointment date says nothing about who you are).
- Any direct identifier left (name, phone, email, ID, card) -> level DIRECT.
- Otherwise: k < 5 -> HIGH (the usual k-anonymity line), k < 1000 -> MEDIUM, else LOW.
- Score for the UI = min(1, 1/k).

Examples: gender + exact age + city ~1,750 (LOW); gender + DOB + PIN ~1 (HIGH).

## Consequences
- Independence is an approximation: age and city are not independent, real values are not uniform (a big city hides you better than a village). The score is a ranking signal, not a probability.
- Generalizing a value (age 34 -> 30-35) visibly raises k, which gives the utility policy a measurable reason to generalize instead of redact.
- Shares are constants for now; a later version could use census tables per city.
