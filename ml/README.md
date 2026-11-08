# ML

NER training and evaluation (M1).

## Get the data
```bash
pip install -r ml/requirements.txt
python ml/scripts/fetch_ai4privacy.py --limit 2000
```
Writes `data/raw/ai4privacy_en_{train,validation}.jsonl` (git-ignored) and prints label counts.

Model weights go in `ml/models/` (git-ignored).

Dataset: ai4privacy/open-pii-masking-500k (CC-BY-4.0). Cite Ai4Privacy in any report. See ADR-0009.
