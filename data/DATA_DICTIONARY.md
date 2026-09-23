# FinSight AI — Data Dictionary

All datasets are synthetic. See `README.md` for the disclosure statement.

---

## `company_financials.csv` / `company_financials.xlsx`

One row = one company's financials for one reporting quarter.

| Column | Type | Description |
|---|---|---|
| `company_id` | string | Synthetic company identifier, e.g. `C001`. Stable across periods. |
| `company_name` | string | Synthetic company name. |
| `sector` | string | One of 14 synthetic sector categories (e.g. "Logistics & Transport", "IT Services"). Drives baseline exposure assumptions. |
| `currency` | string | Reporting currency. All rows use `USD` in this dataset. |
| `period_label` | string | Reporting period, e.g. `2024-Q2`. |
| `period_start`, `period_end` | date (`YYYY-MM-DD`) | Period boundaries. |
| `revenue` | float | Total revenue for the period. |
| `cogs` | float | Cost of goods sold. |
| `operating_expenses` | float | SG&A / operating expenses (excludes COGS and interest). |
| `interest_expense` | float | Interest paid on debt for the period. |
| `net_income` | float | Bottom-line profit/loss after interest and tax. Can be negative. |
| `current_assets` | float | Total current assets. |
| `current_liabilities` | float | Total current liabilities. |
| `inventory` | float | Inventory, a subset of current assets (used for Quick Ratio). |
| `total_debt` | float | Total interest-bearing debt (short + long-term). |
| `total_equity` | float | Total shareholders' equity. |
| `cash_and_equivalents` | float | Cash + short-term investments, a subset of current assets. |
| `operating_cash_flow` | float | Cash generated from operations for the period. |
| `oil_energy_exposure_pct` | float, 0–1 | Fraction of COGS sensitive to oil/energy price moves. Used by the `oil_price_shock` scenario. |
| `import_cost_exposure_pct` | float, 0–1 | Fraction of COGS sourced via imports (FX-sensitive cost). Used by `currency_depreciation`. |
| `export_revenue_exposure_pct` | float, 0–1 | Fraction of revenue from exports (FX-sensitive revenue). Used by `currency_depreciation`. |
| `fx_debt_exposure_pct` | float, 0–1 | Fraction of debt-service cost effectively FX-denominated. Used by `currency_depreciation`. |
| `variable_rate_debt_pct` | float, 0–1 | Fraction of `total_debt` at a variable (not fixed) interest rate. Used by `interest_rate_hike`. |
| `demand_sensitivity_index` | float, typically 0.4–2.0 | Multiplier on how strongly revenue responds to a demand shock (1.0 = proportional). Used by `demand_slowdown`. |
| `variable_cost_ratio` | float, 0–1 | Fraction of COGS that scales with volume (vs. fixed). Used by `demand_slowdown` to shrink COGS less than revenue. |

**Note:** the seven `*_exposure_pct` / `*_index` / `*_ratio` columns are what the Scenario Simulation Engine calls a company's "exposure fields" — they are what make each scenario company-specific instead of a flat across-the-board KPI adjustment.

---

## `macro_indicators.csv`

One row per reporting quarter — synthetic macro backdrop, for reference/documentation only.

| Column | Type | Description |
|---|---|---|
| `period_label` | string | Matches `company_financials.period_label`. |
| `period_start`, `period_end` | date | Period boundaries. |
| `inflation_rate_pct` | float | Synthetic annualized inflation rate for the period. |
| `policy_interest_rate_pct` | float | Synthetic central-bank policy rate for the period. |
| `oil_price_usd_per_bbl` | float | Synthetic oil price. |
| `fx_index_local_per_usd` | float | Synthetic FX index (higher = weaker local currency), indexed to 100 at the first period. |

---

## `scenario_assumptions.csv`

One row per scenario type — the documented transmission rule.

| Column | Type | Description |
|---|---|---|
| `scenario_type` | string | One of: `oil_price_shock`, `currency_depreciation`, `interest_rate_hike`, `demand_slowdown`, `combined_stress`. |
| `default_magnitude` | float or text | The magnitude used if the API caller doesn't supply one. |
| `magnitude_meaning` | string | Plain-English definition of what the magnitude number means for this scenario. |
| `affected_line_item` | string | Which financial statement line item(s) this scenario adjusts. |
| `transmission_field` | string | Which company exposure field(s) from `company_financials.csv` drive the size of the adjustment. |
| `formula` | string | The exact deterministic formula applied — mirrors `backend/app/services/scenario_assumptions.py`. |
| `rationale` | string | Why this transmission mechanism was chosen — the "why," for interview defense. |

---

## `ml_risk_training.csv`

One row = one synthetic company-period feature vector + rule-based risk label. **Not consumed by the current build phase.**

| Column | Type | Description |
|---|---|---|
| `sample_id` | string | Synthetic row identifier. |
| `net_margin`, `operating_margin`, `gross_margin` | float | Synthetic profitability ratios. |
| `current_ratio`, `quick_ratio` | float | Synthetic liquidity ratios. |
| `debt_to_equity` | float | Synthetic leverage ratio. |
| `interest_coverage` | float | Synthetic leverage/coverage ratio. |
| `operating_cash_flow_margin` | float | Synthetic cash-flow ratio. |
| `revenue_growth` | float | Synthetic period-over-period revenue growth. |
| `composite_health_score` | float, 0–100 | The rule-based composite score used to derive `risk_label` (same weighting logic as the product's Financial Health Score: 30% profitability, 25% liquidity, 25% leverage, 20% cash flow). |
| `risk_label` | string | `Low` (score ≥ 65), `Medium` (40 ≤ score < 65), or `High` (score < 40). Rule-based, not human- or model-labelled. |
