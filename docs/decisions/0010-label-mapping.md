# ADR-0010: Mapping ai4privacy labels to our PiiType

- Status: Accepted
- Date: 2026-11-09
- Requirements: FR-07, FR-14

## Context
The 2,000-row English sample has 20 labels (top: GIVENNAME 1661, SURNAME 686, CITY 360). Our PiiType set is smaller and Indian-focused. Findings: no ORG label at all; `locale` is empty for every row, so India-region rows cannot be filtered.

## Decision
| PiiType | ai4privacy labels |
| --- | --- |
| PERSON | GIVENNAME, SURNAME (adjacent parts merged) |
| LOCATION | CITY |
| ADDRESS | STREET, BUILDINGNUM, ZIPCODE (adjacent parts merged) |
| PHONE, EMAIL, CARD, DATE | TELEPHONENUM, EMAIL, CREDITCARDNUMBER, DATE |
| GOV_ID (new) | IDCARDNUM, PASSPORTNUM, DRIVERLICENSENUM, SOCIALNUM, TAXNUM |
| AGE, GENDER (new) | AGE; GENDER, SEX |
| dropped | TITLE, TIME |

Merge rule: same type, PERSON or ADDRESS only, gap of at most 3 chars of space/`,.-/`.
Unknown labels raise an error, so a new dataset version cannot silently drop a type.
Code: `backend/app/detectors/label_map.py`.

## Consequences
- NER cannot find ORG; ORG stays in the enum for rules/LLM later.
- Specific Indian IDs (Aadhaar, PAN) come from rules; NER only flags "some ID" as GOV_ID.
- AGE and GENDER feed the re-identification risk score, not masking by default.
