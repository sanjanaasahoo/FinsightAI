# FinSight AI — Financial Health & Business Impact Analytics

A personal-portfolio-scale financial analytics platform: deterministic financial analytics, transparent scenario simulation, a two-model ML risk classifier, and Gemini-powered explanations. Built with FastAPI + SQLAlchemy + SQLite only — no PostgreSQL, no auth system, no RAG.

> **Status: Financial Analytics + Scenario/Business Impact Engine + ML Risk Module + Gemini AI Insights all implemented.**
> Upload → validate → persist → compute KPIs/Health Score/trend → simulate scenarios → classify risk → explain with Gemini is fully working end-to-end. Authentication, the RAG/document-Q&A layer, and the dashboard UI are **not** implemented yet — see Section 9.

---

## 1. What FinSight AI Actually Does (Current Workflow)

1. **Upload** a CSV or XLSX of company financial statements (`POST /api/statements/upload`) — one file can contain many companies and many reporting periods at once.
2. **Validation** runs per-row: required columns, numeric types, non-negative balance-sheet fields, exposure percentages in [0,1], sane date ranges. A bad row is skipped and reported; the rest of the file still ingests. A duplicate `(company_id, period_label)` *within the same file* is treated as an update to the first occurrence, not a conflicting second insert.
3. **Persistence**: each row upserts a `Company` (by `company_id`) and a `FinancialStatement` (by `company_id` + `period_label`) into SQLite via SQLAlchemy. Re-uploading the same period overwrites it — no duplicates.
4. **Financial Analytics** (`POST /api/analyses/{statement_id}`): computes 9 KPIs/ratios and a 0–100 **Financial Health Score** with a fully itemized breakdown (see Section 3).
5. **Trend analysis** (`GET /api/analyses/company/{company_id}/trend`): period-over-period % change and direction (improving/declining/stable) for every tracked metric, across all of a company's uploaded periods.
6. **Scenario simulation** (`POST /api/scenarios/simulate`): applies one of four macro shocks to a statement, using the *company's own exposure fields* to determine the size of the impact — not a flat, company-agnostic adjustment (see Section 4).
7. **Combined stress test** (`POST /api/scenarios/stress-test`): all four shocks applied additively to the same base case.
8. **Business Impact**: every scenario call returns Base Case vs Scenario Case for every KPI and for revenue/cost/profit/cash-flow line items, the Health Score delta, and a ranked "most affected metrics" list.
9. **ML risk classification** (`POST /api/risk/assess`): classifies Low/Medium/High risk from the computed KPIs — for a statement's base case, or for a specific scenario run — using whichever of two trained models actually performed better (see Section 5).
10. **Gemini AI insights** (`POST /api/insights/summary`, `POST /api/insights/ask`): takes the already-computed KPIs, Health Score, scenario impact, and risk classification and asks Gemini to *explain* them in plain English — Gemini never calculates a number itself (see Section 6).

---

## 2. Project Structure

```
finsight-ai/
├── data/                          # synthetic demo dataset — see data/README.md
│   ├── company_financials.csv     # 20 companies x 8 quarters = 160 rows — upload this
│   ├── company_financials.xlsx    # same data, Excel format
│   ├── macro_indicators.csv       # reference-only macro backdrop
│   ├── scenario_assumptions.csv   # human-readable scenario formulas (mirrors the executed code)
│   ├── ml_risk_training.csv       # 600-row synthetic training set — used by app/ml/train_model.py
│   ├── generate_dataset.py        # regenerate all of the above (fixed seed = reproducible)
│   ├── README.md
│   └── DATA_DICTIONARY.md
├── backend/
│   ├── app/
│   │   ├── main.py                 # app factory, lifespan startup, router wiring
│   │   ├── core/                   # config, logging
│   │   ├── db/
│   │   │   ├── database.py         # engine/session/Base
│   │   │   └── models.py           # Company, FinancialStatement, Analysis, ScenarioRun, RiskAssessment
│   │   ├── routers/
│   │   │   ├── statements_router.py   # upload, get statement
│   │   │   ├── companies_router.py    # list companies, list a company's statements
│   │   │   ├── analyses_router.py     # run/get analysis, company trend
│   │   │   ├── scenarios_router.py    # scenario types, simulate, stress-test, retrieval
│   │   │   ├── risk_router.py         # ML risk assessment, model-info
│   │   │   └── insights_router.py     # Gemini summary + Q&A
│   │   ├── services/
│   │   │   ├── validation_service.py     # file/row validation
│   │   │   ├── ingestion_service.py      # upsert into SQLite
│   │   │   ├── analytics_engine.py       # KPIs, Health Score, trend
│   │   │   ├── scenario_assumptions.py   # documented, EXECUTED scenario formulas
│   │   │   ├── scenario_engine.py        # applies a scenario to a statement
│   │   │   ├── impact_engine.py          # Base vs Scenario comparison
│   │   │   ├── ml_risk_service.py        # runtime inference over the trained model
│   │   │   └── gemini_service.py         # Gemini calls — explanation only, never calculation
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── ml/
│   │   │   ├── train_model.py            # offline training script (LogReg vs Random Forest)
│   │   │   ├── risk_model.joblib         # trained model bundle (committed — ready to use)
│   │   │   └── risk_model.summary.json   # human-readable copy of the same bundle's metadata
│   │   ├── rag/                    # empty — reserved, NOT being built now
│   │   └── exceptions/
│   ├── scripts/
│   │   └── seed_from_data.py       # load data/company_financials.csv without curl
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/                       # React + Vite + Tailwind (connectivity-check shell only — no dashboard UI yet)
└── README.md                       # you are here
```

---

## 3. Financial Analytics — What's Computed

**KPIs** (`app/services/analytics_engine.py::compute_kpis`): Revenue Growth, Gross Margin, Operating Margin, Net Margin, Current Ratio, Quick Ratio, Debt-to-Equity, Interest Coverage, Operating Cash Flow Margin. Any ratio with a ~zero denominator returns `None` (never a divide-by-zero crash, never a fabricated number).

**Financial Health Score (0–100)**: a weighted sum of four components —

| Component | Weight | Metrics |
|---|---|---|
| Profitability | 30% | Net Margin, Operating Margin, Gross Margin |
| Liquidity | 25% | Current Ratio, Quick Ratio |
| Leverage | 25% | Debt-to-Equity (inverted), Interest Coverage |
| Cash Flow | 20% | Operating Cash Flow Margin |

Each metric is normalized to 0–100 against a **fixed, documented band**, not learned from data, so the score is fully explainable. A missing/undefined ratio normalizes to 0 (never silently excluded).

**Trend analysis**: period-over-period % change plus a direction label derived from a NumPy linear-fit slope.

---

## 4. Scenario Simulation — What's Modelled and Why

Four individual scenarios plus one combined stress test, each transforming the statement using the **company's own exposure fields** — see `data/scenario_assumptions.csv` (human-readable) and `app/services/scenario_assumptions.py` (executed, kept consistent).

| Scenario | Default | Mechanism |
|---|---|---|
| `oil_price_shock` | +20% | `cogs *= (1 + oil_energy_exposure_pct * magnitude)` |
| `currency_depreciation` | +10% | `cogs`, `revenue`, and `interest_expense` each move by their own exposure field × magnitude |
| `interest_rate_hike` | +2pp | Only the **variable-rate share** of debt reprices |
| `demand_slowdown` | −15% | `revenue` falls by the shock × sensitivity; `cogs` falls by less (fixed-cost cushion) |
| `combined_stress` | n/a | Each scenario's **independent dollar delta** summed — additive, not sequential/compounded |

**Deliberately-disclosed nuance on `currency_depreciation`:** unlike the other three, it's not universally adverse — a genuine net exporter can come out ahead. `tests/test_impact_engine.py` has dedicated tests proving both directions on purpose.

**Business Impact** (`app/services/impact_engine.py`) re-runs the *exact same* KPI/Health-Score logic on the scenario-adjusted statement, then diffs every KPI and line item. "Most affected metrics" are ranked by health-score-point change (KPIs) or dollar-change-as-%-of-revenue (line items) — not raw % change, which is unstable near a zero base.

---

## 5. ML Risk Module — Two Models, Compared Honestly

**Task:** classify financial risk as Low / Medium / High from 9 already-computed KPIs (never raw statement fields).

**Models trained and compared** (`app/ml/train_model.py`, run offline — not at request time):
1. **Logistic Regression** — the linear baseline, `class_weight='balanced'` (see why below).
2. **Random Forest** — the nonlinear comparison model, 300 trees, unbounded depth.

Both are trained on an 80/20 split of `data/ml_risk_training.csv` and evaluated on the held-out 20% with **accuracy, precision, recall, F1 (macro and per-class), and a confusion matrix**. The model with the higher **macro F1** (chosen because the classes are imbalanced — "Low" is the rarest at ~14% — and macro F1 doesn't let a model coast by ignoring the minority class) is selected, then **refit on the full dataset** for deployment.

### The actual, honest result

**Logistic Regression wins — clearly and consistently.** Across every hyperparameter combination tried during development, Logistic Regression's macro F1 (0.88–0.95) beat Random Forest's (0.78–0.84). This is not a fluke: `data/generate_dataset.py` labels `risk_label` using a **linear weighted composite** of the same normalized features used as model inputs here — a linear model has a structural advantage at recovering a linear rule. The training script doesn't hardcode this outcome — it picks whichever model wins on the actual held-out numbers — but on this dataset, that's Logistic Regression every time. This is a genuinely useful finding: it's evidence that model selection should be driven by evaluation, not by assuming "more complex = better."

**Feature importance** (from the selected model — coefficient magnitude for Logistic Regression, since it was trained on standardized inputs; `feature_importances_` for Random Forest) is returned with every prediction and via `GET /api/risk/model/info`, ranked and shown as a percentage of total importance.

**Missing-value handling:** a `None` KPI (e.g. `revenue_growth` on a company's first uploaded period) is imputed with that feature's training-data median — disclosed explicitly in every response via `imputed_features`, never silently substituted.

**⚠️ The training labels are SYNTHETIC.** `risk_label` in `data/ml_risk_training.csv` is a rule-based proof-of-concept label (see `data/generate_dataset.py` and `data/DATA_DICTIONARY.md`), not derived from real credit events, real defaults, or real analyst judgment. Every API response carries a `training_data_disclaimer` field saying exactly this — treat the model's output as a demonstration of the ML pipeline, not a validated real-world risk score.

**Leakage guard:** `composite_health_score` — the column the synthetic labels were literally thresholded from — is deliberately **excluded** from the model's features. Including it would let the model trivially learn the threshold rule instead of a genuine relationship between ratios and risk.

### Training the model

```bash
cd backend
python3 -m app.ml.train_model
```

Prints both models' full metrics, which one was selected and why, and writes `app/ml/risk_model.joblib` (used at inference time) plus `app/ml/risk_model.summary.json` (the same metadata, human-readable — handy to open directly). **A trained model is already committed** in this repo, so `POST /api/risk/assess` works immediately without running this first — re-run it any time (e.g. after regenerating the dataset) to refresh it.

---

## 6. Gemini AI Insights — Explanation Only, Never Calculation

**The one rule this module exists to enforce: Gemini never calculates, recomputes, or invents a financial number.** It receives a structured JSON object of results the backend has *already computed* — KPIs, Health Score breakdown, scenario impact (if applicable), and ML risk classification — and is instructed, via a strict system prompt, to explain them, never to produce new figures. Every number Gemini mentions must come from that JSON; if it can't answer from the given data, it's instructed to say so rather than guess.

Two endpoints:
- **`POST /api/insights/summary`** — `{statement_id, scenario_run_id?}` → `{overall_insight, risk_drivers, scenario_explanation, recommendations, risk_category, risk_confidence, model_used}`. The last three fields come from the real, independently-computed ML risk service, not from Gemini.
- **`POST /api/insights/ask`** — `{statement_id, scenario_run_id?, question}` → `{question, answer}`, a free-form answer grounded in the same structured context.

**SDK:** the current, GA `google-genai` package (`from google import genai`) — not the deprecated `google-generativeai`. **The API key is never in source code or frontend code** — it's read exclusively from `GEMINI_API_KEY` via `app/core/config.py`'s environment-backed settings.

**Graceful degradation:** if `GEMINI_API_KEY` isn't set, both endpoints return a clean **HTTP 503** with a clear message ("AI insights not configured...") — never an unhandled crash, and every other endpoint in the platform keeps working normally regardless.

**Known, disclosed scope limitation:** guardrails here are prompt-level only (the strict system instruction above) — there is no separate post-hoc layer that cross-checks every number Gemini outputs against the source JSON. That kind of numeric-hallucination guardrail is a reasonable future enhancement, deliberately left out to keep this phase simple, per the project's "no new infrastructure" scope.

---

## 7. What Broke During Development (kept here on purpose)

Four real bugs were found by hand-verifying the code against actual data, not caught by intuition alone:

1. **Cash-flow sign flip** (Business Impact Engine): scaling operating cash flow by the *ratio* of scenario to base net income could flip sign when base net income was negative, making an interest-rate hike appear to *improve* the Health Score. Fixed with an additive dollar-delta instead. Covered by regression tests in `tests/test_impact_engine.py`.
2. **Exploding percentages near zero** (Business Impact Engine): the "most affected metrics" ranking used raw % change, which blows up near a zero base (one real case reported "+1436%"). Fixed by ranking KPIs on bounded Health-Score-point deltas instead.
3. **Duplicate-row-in-one-upload crash risk** (Ingestion Service): with the session's `autoflush=False`, two rows for the same `(company_id, period_label)` within a single upload file would both attempt an INSERT and collide on the unique constraint at commit time, since the second row's "does this exist" check couldn't see the first row's still-unflushed insert. Fixed with an in-batch cache keyed by `(company_id, period_label)`. Covered by `test_duplicate_row_within_a_single_upload_does_not_raise` in `tests/test_api_integration.py`.
4. **Import-order bug** (Gemini Service): the original `_call_gemini` imported `google.genai.types` *before* checking whether `GEMINI_API_KEY` was configured, so a missing key produced a confusing `ModuleNotFoundError` (on environments without the SDK installed) instead of the intended clear "not configured" error. Fixed by checking the key first. Covered by `test_missing_api_key_raises_clear_ai_service_error` in `tests/test_gemini_service.py`.

---

## 8. Setup & Run

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# optional: edit .env and set GEMINI_API_KEY to enable AI insights
uvicorn app.main:app --reload
```

The API is at **http://localhost:8000**, interactive docs at **http://localhost:8000/docs**.

**Load the demo dataset** (either works):

```bash
# Option A — via the actual upload endpoint
curl -X POST http://localhost:8000/api/statements/upload \
  -F "file=@../data/company_financials.csv"

# Option B — convenience script (same code path, no curl needed)
python3 scripts/seed_from_data.py
```

**Train the ML model** (optional — a trained model is already committed):

```bash
python3 -m app.ml.train_model
```

**Frontend** (unchanged shell — no dashboard UI yet, just a connectivity check):

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

### Running tests

```bash
cd backend
pytest -v
```

---

## 9. What's Implemented vs Not

### Implemented
- [x] CSV/XLSX upload with per-row validation, clear error reporting, and duplicate-row-in-one-file handling
- [x] SQLite persistence via SQLAlchemy (Company, FinancialStatement, Analysis, ScenarioRun, RiskAssessment)
- [x] Financial Analytics Engine: 9 KPIs, 0–100 Health Score with full breakdown, trend analysis
- [x] Scenario Simulation Engine: 4 scenarios + combined stress, exposure-field-driven
- [x] Business Impact Engine: Base vs Scenario diff, most-affected ranking
- [x] ML Risk Module: Logistic Regression vs Random Forest, evaluated and selected by held-out macro F1, feature importance, synthetic-label disclosure
- [x] Gemini AI Insights: executive summary + free-form Q&A, explanation-only, graceful degradation without an API key
- [x] Full REST API (statements, companies, analyses, scenarios, risk, insights)
- [x] Synthetic demo dataset: 160 company-periods, macro reference data, documented scenario assumptions, 600-row ML training set
- [x] Test suite: validation, KPI/Health-Score formulas, scenario formulas, Business Impact regression tests, ML training/inference tests, Gemini service tests (fully mocked), API integration tests for every router

### Explicitly NOT implemented
- Authentication (no JWT, no login — not required by anything built so far)
- RAG / document Q&A / PDF ingestion / embeddings / FAISS — not being built in this phase at all
- Dashboard UI — the frontend is still the Phase 1 connectivity-check shell
- A numeric-hallucination guardrail layer for Gemini's output beyond the prompt itself (see Section 6)

---

## 10. Tech Stack (this phase)

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| Database | SQLite via SQLAlchemy ORM — no PostgreSQL |
| Data validation/ingestion | Pandas |
| Analytics/scenario math | Pure Python + NumPy (trend slope only) |
| ML | Scikit-learn (Logistic Regression + Random Forest), joblib for persistence |
| LLM | Gemini API via `google-genai` (current, GA SDK) |
| Testing | Pytest |

`requirements.txt` also lists packages for a possible later RAG phase (sentence-transformers, faiss-cpu, pymupdf) that this build's code does not import or use — pre-declared during infrastructure setup, not because this phase depends on them.
