# Hand-written Indian eval v2 (held-out, P19, D9)

Set: `data/eval/handwritten_v2.txt`, 32 texts, 75 gold spans. Written by a separate AI agent that
never saw the code, the fusion rules or v1's errors; **labels checked by the project owner**. One
fix before scoring: the agent's Aadhaar failed Verhoeff, so its last digit was changed
(`…500` → `…505`) with the owner's approval. Nothing else was changed, before or after scoring.
Strict exact span match; AADHAAR/PAN compared as GOV_ID (ADR-0012).

Run (model: `bohr2222/privacy-guardian-ner` @ `87b84e3`, cached in `data/eval/ner_cache_v2.jsonl`):

    python ml/scripts/eval_handwritten.py --gold data/eval/handwritten_v2.txt \
        --ner-cache data/eval/ner_cache_v2.jsonl --show-errors

| System | Precision | Recall | F1 |
| --- | --- | --- | --- |
| Rules only | 0.944 | 0.227 | 0.366 |
| NER only | 0.604 | 0.733 | 0.663 |
| Rules + NER (greedy baseline) | 0.642 | 0.813 | 0.718 |
| **Fusion (the app)** | **0.744** | **0.853** | **0.795** |

v1 gave 0.976, but v1 was used to design the fusion rules. **0.795 is the honest number.**

## PRD success criterion 2

| Check | Target | Result |
| --- | --- | --- |
| Span F1 on held-out v2 | ≥ 0.90 | **0.795: not met** |
| Precision on checksum types (Aadhaar, card; PAN too) | 1.0 | **1.0: met** (5 of 5 correct) |

## Subset view, chosen after scoring

Requested by the owner after seeing the errors, so it is **not** a held-out number. Left out:
the Devanagari line (23; the model was trained on English only) and four unusual lines that
explain themselves or use an impossible Aadhaar (27 to 30). Same code as the headline.

    python ml/scripts/eval_handwritten.py --gold data/eval/handwritten_v2.txt \
        --ner-cache data/eval/ner_cache_v2.jsonl --skip 23,27,28,29,30

| Set | Texts | Gold items | F1 (fusion) |
| --- | --- | --- | --- |
| Full v2 (headline) | 32 | 75 | **0.795** |
| v2 without those 5 lines | 27 | 69 | 0.822 |

## What a reader sees: is the data hidden?

Exact match is strict: an address found as "street" + "city" counts as a miss and two extra items,
even when every letter is hidden. Counting characters instead (added after scoring, so a
secondary view, not the headline):

| Gold items | Fully hidden | Partly hidden | Left visible |
| --- | --- | --- | --- |
| 75 | 66 | 7 | **2** |

- Left visible: the lowercase Hinglish name `asha` and the Devanagari name `राधा शर्मा`.
- Partly hidden: six addresses show only the `, ` between street and city, and "Flat 8, Green Park
  Apartments" leaves the word `Apartments`. The driving licence leaves one `-`.

## Error groups

1. **Address boundaries (20 of 33 errors).** The gold set puts the city inside the address
   (`5 Lotus Lane, Lucknow`); the app, like the v1 labels, splits street (ADDRESS) and city
   (LOCATION). The v2 instructions did not say which way, so most of these are a labelling
   difference, not a leak. Also `PIN 452016` includes the word PIN. A real one: "Green Park
   Apartments" cut after "Park".
2. **Names the model was not trained for:** lowercase Hinglish (`asha`) and Devanagari script.
   The model learnt from English text only. These are the only real leaks.
3. **Harmless numbers kept:** `OTP 741903` and the amount `399` as GOV_ID; the 10-digit PNR as
   PHONE (it has a valid mobile format). Order and ticket numbers were correctly dropped.
4. **Number that fails the Aadhaar checksum:** rules refuse it, but the model calls it a generic
   GOV_ID and fusion keeps it. Over-hiding, not a leak; checksum-type precision stays 1.0.
5. **Driving licence** `DL-08-2026-0045821` split into GOV_ID + PHONE (no rule for licences).
6. **Wrong type, still hidden:** `Kochi` as PERSON.
7. **Debatable gold:** in "The word Kiran appears…" and "I saw the word Asha…", the gold marks
   only the second mention; the app hides both.

## Limits

- 32 texts, 75 items: one or two items move F1 by about 0.01 to 0.02.
- Written by an AI from a short prompt, so the style is more regular than real documents. Three
  lines explain themselves ("…should not be marked"), and the bad Aadhaar starts with 1, which a
  real Aadhaar never does, so those cases are easy.
- One requested case is missing: an email inside a URL.

## After the address fix (ADR-0024), 2026-11-26

The address rule is now written down: street to city is one ADDRESS, a PIN stays apart, a cut
building word is pulled back in, and label words (PIN, OTP) are trimmed from values. v1 labels
were updated to the same rule (3 lines).

| Set | Before | After | Held out? |
| --- | --- | --- | --- |
| v1 (32 texts) | 0.976 | 0.975 | No: used to design fusion |
| v2 full (32 texts) | **0.795** | 0.922 | **No longer**: its errors guided this fix |
| v2 subset (27 texts) | 0.822 | 0.943 | No |

What changed on v2: all 9 addresses now match; `OTP 741903` is no longer kept. Character
view after the fix: 72 of 75 fully hidden, 1 partly (one `-` in the licence), 2 left visible
(the same two names). Still open: Hinglish and Devanagari names, the PNR read as a phone, the
amount `399`, the driving licence split, the impossible Aadhaar kept as GOV_ID.

## Rule from here (D9)

The honest held-out number is still **0.795**. To quote the improved code, write a new set v3
the same way (a different author, never shown the code or these errors, the address rule from
ADR-0024 in the prompt), score it once, and quote that.
