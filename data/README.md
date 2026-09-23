# FinSight AI — `/data` folder

This folder contains the **demo dataset** used to build and test FinSight AI's financial analytics and scenario engine.

## ⚠️ This data is synthetic

Every number in this folder is **fabricated** by `generate_dataset.py`, using a fixed random seed (42) for reproducibility. **None of it is real company data, and none of it should be presented, cited, or treated as real-world financial or macroeconomic data.** Company names, financials, sector exposure profiles, and macro indicators are all generated.

Sector-level baseline assumptions (e.g. "logistics companies tend to have higher oil/energy cost exposure than IT services companies") are loosely informed by general public knowledge of how these sectors behave — but the specific numbers assigned to each synthetic company are fabricated for this project, not sourced from any real company's filings.

**Future direction:** the project is structured so that real public financial statements (e.g. company 10-Ks/annual reports) and real macro data (e.g. published inflation, interest rate, oil price, FX series) could later be substituted in or used to sanity-check these assumptions — but that substitution has not been done yet.

## Files

| File | Rows | Purpose |
|---|---|---|
| `company_financials.csv` | 160 | Primary demo dataset — 20 synthetic companies x 8 quarters (2023 Q1 – 2024 Q4). This is what you upload through `/api/statements/upload`. |
| `company_financials.xlsx` | 160 | Identical data, Excel format — used to test/demo the `.xlsx` upload path. |
| `macro_indicators.csv` | 8 | One row per quarter: synthetic inflation, policy interest rate, oil price, and FX index. Reference/context only — **not** read directly by the scenario engine (see below). |
| `scenario_assumptions.csv` | 5 | Human-readable documentation of exactly how each scenario transforms the financials. This must match `backend/app/services/scenario_assumptions.py` — the CSV is the "read this in an interview" copy, the Python file is the "actually executed" copy. |
| `ml_risk_training.csv` | 600 | A separate, larger synthetic dataset of already-computed KPI feature vectors + a rule-based Low/Medium/High risk label. **Not used by the current build phase** (no ML endpoint exists yet) — prepared now so a future ML phase has ready, documented training data. |

## Why macro_indicators.csv isn't "wired in" yet

The scenario engine (`backend/app/services/scenario_engine.py`) takes its magnitude for each scenario (e.g. "+20% oil price") either as a request parameter or from a documented default in `scenario_assumptions.py` — it does **not** read `macro_indicators.csv` at request time. That file exists to give the demo a realistic macro backdrop you can point to ("here's what a +20% oil shock roughly corresponds to historically") without making the scenario engine depend on a specific dataset's shape. Wiring macro data in as a *source of default magnitudes* (rather than just a documentation reference) is listed as a future enhancement.

## Why ml_risk_training.csv exists but isn't used yet

The current build phase is Financial Analytics + Scenario/Business Impact only. The ML risk classifier (Random Forest, per the architecture document) is a later phase. This file is generated now, alongside the rest of the dataset, so that phase can start immediately with a ready, clearly-labelled, rule-based-labelled synthetic training set rather than needing its own data-generation effort. Its labelling rule is documented in `generate_dataset.py` and mirrors the same normalization logic as the Financial Health Score, for consistency.

## Regenerating the data

```bash
cd data
python3 generate_dataset.py
```

This overwrites all five generated files deterministically (same seed → identical output every time).

See `DATA_DICTIONARY.md` for full column-level definitions.
