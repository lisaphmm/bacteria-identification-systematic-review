# Deep learning for bacterial image analysis: systematic review (title/abstract screening)

## Pipeline

1. **Search and export**: `scopus.csv`, `pubmed.txt`, `ieeexplore.csv`, `springerlink.csv`, `embase.csv`. Search strategy and eligibility criteria: `AI-Bacteria Word Search Strategy.xlsx`.
2. **Deduplicate**: `deduplicate.py` -> `deduplicated_papers.csv`, `deduplication_log.csv`.
3. **Prepare**: `prepare_screening_set.py` -> `to_screen.csv` (records sent to the models) and `excluded_records.csv` (records removed before screening, with the reason: no abstract, before 2015, after the 2026-10-13 cut-off).
4. **Screen with two LLMs** (Gemini and Mistral, blind to each other): `screening_pipeline.py screen`. Prompt: `bacteria_screening_instructions.txt`. Settings: `config.py`. Results are checkpointed in `results_gemini.jsonl` and `results_mistral.jsonl` (re-running skips finished records).
5. **Pilot**: 300 records (`pilot_300.csv`). The author screened 100 blind (`pilot_manual_check.xlsx`) and resolved the model-flagged ones (`pilot_check_manually.xlsx`, `pilot_review_decisions.csv`). Combined table: `pilot_final.csv` (`screening_pipeline.py merge-pilot`).
6. **Full run, review, final file**: `screening_pipeline.py export` builds `screening_review.xlsx`. Where the two models disagree, or either one cannot confirm a deep learning method, the paper goes to the manual check list. `screening_pipeline.py finalize` writes `final_results.csv` (pilot + full), `final_included_papers.csv` and `prisma_counts.txt`.

## Setup

```
python -m venv .venv && .venv/bin/pip install pandas requests openpyxl
```

Create `.env` (never committed) with `GEMINI_API_KEY=` and `MISTRAL_API_KEY=`. `python screening_pipeline.py check-models` verifies the model IDs. The full run stays locked until `PILOT_APPROVED = True` in `config.py`.
