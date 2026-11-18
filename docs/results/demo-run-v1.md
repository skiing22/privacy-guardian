# First real-model run of the full graph (CLI demo)

`python -m app.cli scan ../data/samples/patient_note.txt` on a Windows laptop (CPU), NER v1.
All unit tests passed before this run; the real model still exposed 4 bugs.

| # | Seen in output | Cause | Fix | Regression test |
| --- | --- | --- | --- | --- |
| 1 | `age [REDACTED]-[REDACTED]`, 3 rounds | Verifier found "30" and "34" inside the generalized "30-34" and called them leaks | `filter_known` ignores anything inside an allowed value's occurrence | `test_pieces_of_a_generalized_value_are_not_leaks` |
| 2 | `LOCATION_2: PERSON_1` (word "Patient" lost, lines merged) | NER joined "Kozhikode\nPatient" across a line break | `fuse.clean` cuts any span at the first line break | `test_span_never_crosses_a_line_break` |
| 3 | `18**-***-**00` | Policy kept the toll-free number, then the risk loop counted it as a personal phone and masked it | Business numbers are excluded from risk and never strengthened | `test_business_number_not_overruled_by_risk_loop` |
| 4 | `risk LOW, clues: none` though "Male" was visible | Final risk came from the last round's 1 span only | `finalize` re-assesses what round 1 left visible (upper bound) | `test_final_risk_covers_whole_document_not_last_round` |

Also: NER showed 29,327 ms, which was model loading, not inference (~110 ms per call). The CLI now loads the model before the scan.

Known, not fixed: "Sunrise" (a hospital name) tagged LOCATION, because the training data has no ORG label (ADR-0010).

Lesson: unit tests check each part against what we expected; an end-to-end run with the real model checks what actually happens.

## CSV run (`employees.csv --columns --auto`)
| # | Seen | Cause | Fix |
| --- | --- | --- | --- |
| 5 | Column `mobile` = GOV_ID, `joined` = ADDRESS, `emp_id` = ADDRESS | Column classifier used NER alone (threshold 0.3), skipping rules and fusion | Classify columns with rules + NER + context + fusion (`fused_detector`); test `test_columns_use_fused_detection_not_ner_alone` |

Open (later): employee IDs E102-E104 were pseudonymized but E101 was kept, so one column got inconsistent treatment. Planned: apply one action to a whole column once it is classified (FR-04), and score risk per CSV row (each row is one person), not over the whole file.
