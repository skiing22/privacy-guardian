# NER v1 results

Model: distilbert-base-cased, 50k English ai4privacy rows, 2 epochs, Colab T4 (ADR-0011).
Weights: Google Drive `privacy-guardian/ner-distilbert-v1` (not in git).
Metric: exact span match on 5,000 held-out validation rows (start, end and type must all match).

| Type | Precision | Recall | F1 | Count |
| --- | --- | --- | --- | --- |
| ALL | 0.976 | 0.980 | 0.978 | 9695 |
| DATE | 0.999 | 0.999 | 0.999 | 751 |
| EMAIL | 0.997 | 0.997 | 0.997 | 593 |
| GENDER | 0.993 | 0.989 | 0.991 | 270 |
| PERSON | 0.985 | 0.990 | 0.988 | 4368 |
| GOV_ID | 0.980 | 0.978 | 0.979 | 909 |
| ADDRESS | 0.961 | 0.958 | 0.960 | 866 |
| AGE | 0.947 | 0.963 | 0.955 | 295 |
| LOCATION | 0.947 | 0.959 | 0.953 | 824 |
| CARD | 0.963 | 0.928 | 0.945 | 83 |
| PHONE | 0.933 | 0.947 | 0.940 | 736 |

## Hand-checked Indian samples
- Found correctly: Priya Venkataraman, Kozhikode, 98470 12345, email, Arjun Nair, age 34, 12/03/2026, 14 MG Road, Kochi.
- Errors: "Patient Arjun Nair" (role word included; now trimmed in `NerDetector`); PIN 682016 found as a separate, low-confidence (0.63) ADDRESS.

## Caveats
- Validation data comes from the same synthetic generator as training, so these scores are optimistic. A hand-written test set is still needed before claiming NFR-01 on real text.
- PHONE and CARD are the weakest NER types; the rule detector (checksums) covers them, and fusion combines both.
