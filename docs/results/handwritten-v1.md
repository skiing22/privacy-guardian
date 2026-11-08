# Hand-written Indian eval v1 (M1 baseline)

Set: `data/eval/handwritten_v1.txt`, 32 texts, 63 gold spans. Strict exact span match. AADHAAR/PAN compared as GOV_ID (ADR-0012).
Run: `python ml/scripts/eval_handwritten.py --show-errors`

| System | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Rules only | 1.000 | 0.286 | 0.444 |
| NER only | 0.592 | 0.714 | 0.647 |
| Rules + NER (greedy baseline) | 0.697 | 0.841 | 0.763 |

Synthetic validation F1 was 0.978 (`ner-v1.md`): the gap is the real-world drop.

## Error groups (input for M2)
1. **Combiner trusts the wrong source.** Rules validated `09447012345`, `7012345678` (PHONE) and `SBIN0070123` (IFSC), but NER said GOV_ID with a higher score and greedy kept NER. Fix: source reliability in fusion; a passed checksum/format beats a model guess (FR-11, FR-12).
2. **NER flags harmless numbers:** OTP, order no., train no., room 204, "Android 14", "1111". Synthetic training data has almost no non-PII numbers. Fix: context keywords (FR-08); later, synthetic negatives (ADR-0007).
3. **Indian addresses split:** "22, Nehru Nagar" -> 3 pieces; "Flat 3B, Green Park" -> 2. Fix: merge adjacent ADDRESS spans in fusion.
4. **Keyword words tagged:** "Aadhaar" as PERSON / GOV_ID. Fix: stopword filter.
5. **Boundary only:** "Monday, 16 November 2026" found as "16 November 2026". Fix: also report partial-overlap scores.
6. **Debatable:** toll-free `1800-425-3800`, masked account `XX4521` flagged. Business numbers are not personal; decide in policy.
7. **Missed:** "Neha Kapoor" after a UPI ID; landline `0495 2723456` (rules cover mobiles only).

## M2 target
Rules + fusion must beat F1 0.763 on this set without lowering rules' precision on checksum types.
