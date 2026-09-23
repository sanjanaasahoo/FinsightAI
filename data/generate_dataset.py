"""
generate_dataset.py — FinSight AI synthetic data generator.

Produces the entire /data folder:
  - company_financials.csv / .xlsx  (20 companies x 8 quarters = 160 rows)
  - macro_indicators.csv            (8 quarters of macro context)
  - scenario_assumptions.csv        (documented scenario transmission rules)
  - ml_risk_training.csv            (600-row synthetic training set for a future ML phase)

ALL data here is synthetic, generated with a fixed random seed (42) for
reproducibility. Nothing here is real company or real macroeconomic data.
Sector-level baseline assumptions (typical margins, exposure ranges) are
loosely informed by public knowledge of how these sectors generally behave,
but the specific numbers are fabricated for this project. See data/README.md
and data/DATA_DICTIONARY.md for full documentation.
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG = np.random.default_rng(42)

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# 1. Company universe — 20 companies across 14 sectors, each with a
#    sector-informed baseline exposure profile (oil/energy, import,
#    export, FX-debt, variable-rate debt, demand sensitivity, variable
#    cost ratio). Real economic intuition, fabricated numbers.
# ---------------------------------------------------------------------

SECTOR_PROFILES = {
    # sector: (gross_margin, opex_pct, oil_exp, import_exp, export_exp, fx_debt_exp, var_rate_debt, demand_sens, var_cost_ratio, base_current_ratio, base_de_ratio)
    "Logistics & Transport":     (0.22, 0.14, 0.55, 0.20, 0.10, 0.15, 0.60, 1.30, 0.65, 1.10, 1.40),
    "Energy Trading":            (0.18, 0.10, 0.70, 0.35, 0.15, 0.30, 0.55, 1.10, 0.75, 1.30, 1.60),
    "Import-Export Trading":     (0.20, 0.12, 0.25, 0.60, 0.55, 0.45, 0.40, 1.15, 0.70, 1.20, 1.10),
    "Manufacturing":             (0.32, 0.16, 0.35, 0.30, 0.20, 0.20, 0.45, 1.05, 0.60, 1.40, 0.90),
    "Textiles & Apparel":        (0.28, 0.15, 0.20, 0.45, 0.40, 0.25, 0.35, 1.20, 0.68, 1.30, 0.80),
    "Food Processing":           (0.30, 0.18, 0.25, 0.25, 0.15, 0.15, 0.30, 0.85, 0.62, 1.50, 0.70),
    "Construction Materials":    (0.26, 0.14, 0.45, 0.20, 0.10, 0.15, 0.50, 1.25, 0.58, 1.15, 1.20),
    "Agrochemicals":             (0.34, 0.17, 0.30, 0.35, 0.30, 0.25, 0.35, 0.90, 0.55, 1.45, 0.75),
    "Electronics Assembly":      (0.24, 0.15, 0.15, 0.55, 0.50, 0.30, 0.40, 1.15, 0.72, 1.35, 0.95),
    "Auto Components":           (0.27, 0.15, 0.30, 0.40, 0.35, 0.25, 0.45, 1.20, 0.65, 1.25, 1.05),
    "Packaging":                 (0.29, 0.16, 0.28, 0.25, 0.15, 0.15, 0.35, 0.95, 0.60, 1.40, 0.85),
    "Hospitality":                (0.55, 0.35, 0.12, 0.10, 0.05, 0.10, 0.30, 1.60, 0.35, 0.95, 1.10),
    "IT Services":                (0.62, 0.30, 0.03, 0.05, 0.45, 0.10, 0.15, 0.60, 0.20, 1.90, 0.30),
    "Pharma Distribution":       (0.35, 0.20, 0.10, 0.30, 0.20, 0.15, 0.25, 0.70, 0.50, 1.60, 0.60),
}

COMPANIES = [
    ("C001", "Meridian Freight Lines",        "Logistics & Transport"),
    ("C002", "Alcove Freight Networks",       "Logistics & Transport"),
    ("C003", "Solara Energy Trading Co",      "Energy Trading"),
    ("C004", "Boreal Energy Partners",        "Energy Trading"),
    ("C005", "Cascade Global Trading",        "Import-Export Trading"),
    ("C006", "Harborline Import Exports",     "Import-Export Trading"),
    ("C007", "Northgate Manufacturing",       "Manufacturing"),
    ("C008", "Ironvale Industrial Works",     "Manufacturing"),
    ("C009", "Wovenfield Textiles",           "Textiles & Apparel"),
    ("C010", "Bluepeak Apparel Group",        "Textiles & Apparel"),
    ("C011", "Fernbrook Foods",               "Food Processing"),
    ("C012", "Millstone Food Processors",     "Food Processing"),
    ("C013", "Graniteworks Materials",        "Construction Materials"),
    ("C014", "Stonebridge Building Supply",   "Construction Materials"),
    ("C015", "Verdant Agrochemicals",         "Agrochemicals"),
    ("C016", "Sunridge Electronics Assembly", "Electronics Assembly"),
    ("C017", "Torquehill Auto Components",    "Auto Components"),
    ("C018", "Cedarline Packaging Co",        "Packaging"),
    ("C019", "Lakeside Hospitality Group",    "Hospitality"),
    ("C020", "Brightframe IT Services",       "IT Services"),
]

PERIODS = [
    ("2023-Q1", "2023-01-01", "2023-03-31"),
    ("2023-Q2", "2023-04-01", "2023-06-30"),
    ("2023-Q3", "2023-07-01", "2023-09-30"),
    ("2023-Q4", "2023-10-01", "2023-12-31"),
    ("2024-Q1", "2024-01-01", "2024-03-31"),
    ("2024-Q2", "2024-04-01", "2024-06-30"),
    ("2024-Q3", "2024-07-01", "2024-09-30"),
    ("2024-Q4", "2024-10-01", "2024-12-31"),
]

rows = []
for cid, cname, sector in COMPANIES:
    (gm, opex_pct, oil_exp, import_exp, export_exp, fx_debt_exp,
     var_rate_debt, demand_sens, var_cost_ratio, base_cr, base_de) = SECTOR_PROFILES[sector]

    # Per-company jitter around the sector baseline so companies in the
    # same sector aren't identical (realistic dispersion).
    company_gm = np.clip(gm + RNG.normal(0, 0.02), 0.05, 0.75)
    company_opex_pct = np.clip(opex_pct + RNG.normal(0, 0.015), 0.05, 0.45)
    company_oil_exp = np.clip(oil_exp + RNG.normal(0, 0.05), 0.0, 0.9)
    company_import_exp = np.clip(import_exp + RNG.normal(0, 0.06), 0.0, 0.9)
    company_export_exp = np.clip(export_exp + RNG.normal(0, 0.06), 0.0, 0.9)
    company_fx_debt_exp = np.clip(fx_debt_exp + RNG.normal(0, 0.05), 0.0, 0.8)
    company_var_rate_debt = np.clip(var_rate_debt + RNG.normal(0, 0.08), 0.05, 0.9)
    company_demand_sens = np.clip(demand_sens + RNG.normal(0, 0.1), 0.4, 2.0)
    company_var_cost_ratio = np.clip(var_cost_ratio + RNG.normal(0, 0.05), 0.2, 0.9)
    company_current_ratio_target = np.clip(base_cr + RNG.normal(0, 0.25), 0.5, 2.8)
    company_de_ratio_target = np.clip(base_de + RNG.normal(0, 0.25), 0.1, 2.8)

    # Base revenue scale for this company (in USD, synthetic), plus a
    # per-company growth trend (some grow, some decline, some flat) and
    # quarter-to-quarter noise.
    base_revenue = float(RNG.uniform(8_000_000, 420_000_000))
    quarterly_growth_trend = RNG.normal(0.01, 0.03)  # avg ~1%/quarter, some negative

    revenue = base_revenue
    total_equity = base_revenue * float(RNG.uniform(0.35, 0.9))

    for period_label, period_start, period_end in PERIODS:
        # Revenue evolves with the trend + noise (a few companies get an
        # intentional "bad quarter" for narrative realism).
        shock = 0.0
        if RNG.random() < 0.08:
            shock = RNG.uniform(-0.12, -0.04)  # occasional bad quarter
        revenue = max(revenue * (1 + quarterly_growth_trend + RNG.normal(0, 0.02) + shock), 1_000_000)

        cogs = revenue * (1 - company_gm) * float(RNG.uniform(0.97, 1.03))
        operating_expenses = revenue * company_opex_pct * float(RNG.uniform(0.95, 1.05))
        operating_income = revenue - cogs - operating_expenses

        total_debt = total_equity * company_de_ratio_target * float(RNG.uniform(0.9, 1.1))
        avg_interest_rate = float(RNG.uniform(0.05, 0.09))
        interest_expense = total_debt * avg_interest_rate * float(RNG.uniform(0.9, 1.1))

        pretax_income = operating_income - interest_expense
        tax_rate = 0.25
        net_income = pretax_income * (1 - tax_rate) if pretax_income > 0 else pretax_income

        current_liabilities = revenue * float(RNG.uniform(0.12, 0.22))
        current_assets = current_liabilities * company_current_ratio_target * float(RNG.uniform(0.95, 1.05))
        inventory = current_assets * float(RNG.uniform(0.15, 0.40))
        cash_and_equivalents = current_assets * float(RNG.uniform(0.15, 0.35))

        # Operating cash flow: net income + a depreciation add-back +
        # working-capital noise, so it's correlated with but not equal
        # to net income (realistic).
        depreciation_addback = revenue * float(RNG.uniform(0.015, 0.035))
        working_capital_noise = revenue * RNG.normal(0, 0.01)
        operating_cash_flow = net_income + depreciation_addback + working_capital_noise

        # Slow-drift equity roll-forward (retained earnings effect).
        total_equity = max(total_equity + net_income * float(RNG.uniform(0.3, 0.6)), 1_000_000)

        rows.append({
            "company_id": cid,
            "company_name": cname,
            "sector": sector,
            "currency": "USD",
            "period_label": period_label,
            "period_start": period_start,
            "period_end": period_end,
            "revenue": round(revenue, 2),
            "cogs": round(cogs, 2),
            "operating_expenses": round(operating_expenses, 2),
            "interest_expense": round(interest_expense, 2),
            "net_income": round(net_income, 2),
            "current_assets": round(current_assets, 2),
            "current_liabilities": round(current_liabilities, 2),
            "inventory": round(inventory, 2),
            "total_debt": round(total_debt, 2),
            "total_equity": round(total_equity, 2),
            "cash_and_equivalents": round(cash_and_equivalents, 2),
            "operating_cash_flow": round(operating_cash_flow, 2),
            "oil_energy_exposure_pct": round(float(company_oil_exp), 3),
            "import_cost_exposure_pct": round(float(company_import_exp), 3),
            "export_revenue_exposure_pct": round(float(company_export_exp), 3),
            "fx_debt_exposure_pct": round(float(company_fx_debt_exp), 3),
            "variable_rate_debt_pct": round(float(company_var_rate_debt), 3),
            "demand_sensitivity_index": round(float(company_demand_sens), 3),
            "variable_cost_ratio": round(float(company_var_cost_ratio), 3),
        })

df = pd.DataFrame(rows)
df.to_csv(OUT_DIR / "company_financials.csv", index=False)
df.to_excel(OUT_DIR / "company_financials.xlsx", index=False, sheet_name="company_financials")
print(f"company_financials: {len(df)} rows, {df['company_id'].nunique()} companies")

# ---------------------------------------------------------------------
# 2. Macro indicators — one row per period, for documentation/reference
#    only (not read directly by the scenario engine, which takes
#    magnitude inputs from the API request or scenario_assumptions
#    defaults). Gives a real-world-shaped backdrop to cite in the demo.
# ---------------------------------------------------------------------
macro_rows = []
inflation = 0.045
policy_rate = 0.05
oil_price = 78.0
fx_index = 100.0  # local currency per USD, indexed to 100 at period 1

for period_label, period_start, period_end in PERIODS:
    inflation = max(0.02, inflation + RNG.normal(0, 0.004))
    policy_rate = max(0.02, policy_rate + RNG.normal(0, 0.003))
    oil_price = max(40.0, oil_price * (1 + RNG.normal(0.01, 0.06)))
    fx_index = max(70.0, fx_index * (1 + RNG.normal(0.005, 0.02)))

    macro_rows.append({
        "period_label": period_label,
        "period_start": period_start,
        "period_end": period_end,
        "inflation_rate_pct": round(inflation * 100, 2),
        "policy_interest_rate_pct": round(policy_rate * 100, 2),
        "oil_price_usd_per_bbl": round(oil_price, 2),
        "fx_index_local_per_usd": round(fx_index, 2),
    })

macro_df = pd.DataFrame(macro_rows)
macro_df.to_csv(OUT_DIR / "macro_indicators.csv", index=False)
print(f"macro_indicators: {len(macro_df)} rows")

# ---------------------------------------------------------------------
# 3. Scenario assumptions — documented transmission rules. This is the
#    human-readable mirror of app/services/scenario_assumptions.py;
#    the two must be kept consistent (see data/README.md).
# ---------------------------------------------------------------------
scenario_assumptions_rows = [
    {
        "scenario_type": "oil_price_shock",
        "default_magnitude": 0.20,
        "magnitude_meaning": "relative increase in oil/energy prices (e.g. 0.20 = +20%)",
        "affected_line_item": "cogs",
        "transmission_field": "oil_energy_exposure_pct",
        "formula": "cogs_scenario = cogs_base * (1 + oil_energy_exposure_pct * magnitude)",
        "rationale": "Companies with higher energy/logistics content in COGS (transport, energy, construction) see a larger cost pass-through from an oil price spike.",
    },
    {
        "scenario_type": "currency_depreciation",
        "default_magnitude": 0.10,
        "magnitude_meaning": "relative local-currency depreciation vs USD (e.g. 0.10 = +10% weaker)",
        "affected_line_item": "cogs, revenue, interest_expense",
        "transmission_field": "import_cost_exposure_pct, export_revenue_exposure_pct, fx_debt_exposure_pct",
        "formula": (
            "cogs_scenario = cogs_base * (1 + import_cost_exposure_pct * magnitude); "
            "revenue_scenario = revenue_base * (1 + export_revenue_exposure_pct * magnitude); "
            "interest_expense_scenario = interest_expense_base * (1 + fx_debt_exposure_pct * magnitude)"
        ),
        "rationale": "Depreciation raises the local-currency cost of imported inputs and FX-denominated debt service, but raises local-currency value of export revenue.",
    },
    {
        "scenario_type": "interest_rate_hike",
        "default_magnitude": 0.02,
        "magnitude_meaning": "absolute increase in interest rate, percentage points (e.g. 0.02 = +2pp)",
        "affected_line_item": "interest_expense",
        "transmission_field": "variable_rate_debt_pct",
        "formula": "interest_expense_scenario = interest_expense_base + (total_debt_base * variable_rate_debt_pct * magnitude)",
        "rationale": "Only the variable-rate portion of debt reprices immediately when rates rise; fixed-rate debt is unaffected until refinanced.",
    },
    {
        "scenario_type": "demand_slowdown",
        "default_magnitude": -0.15,
        "magnitude_meaning": "relative change in revenue (e.g. -0.15 = -15%)",
        "affected_line_item": "revenue, cogs",
        "transmission_field": "demand_sensitivity_index, variable_cost_ratio",
        "formula": (
            "revenue_scenario = revenue_base * (1 + magnitude * demand_sensitivity_index); "
            "cogs_scenario = cogs_base * (1 + magnitude * demand_sensitivity_index * variable_cost_ratio)"
        ),
        "rationale": "Revenue falls by the shock scaled by the company's demand sensitivity; COGS falls by less, since only the variable-cost share of COGS shrinks with volume (fixed costs remain).",
    },
    {
        "scenario_type": "combined_stress",
        "default_magnitude": "n/a (uses each scenario's own default)",
        "magnitude_meaning": "applies all four scenarios above",
        "affected_line_item": "cogs, revenue, interest_expense",
        "transmission_field": "all of the above",
        "formula": "Each scenario's dollar-impact (scenario_value - base_value) is computed independently against the SAME base case, then the deltas are summed onto the base case.",
        "rationale": "Kept additive rather than sequential/compounded, since sequential order would arbitrarily change the result and modelling true joint/compounded effects needs a full simulation model — out of scope for this project. This simplification is stated explicitly wherever a combined-stress result is shown.",
    },
]
scenario_df = pd.DataFrame(scenario_assumptions_rows)
scenario_df.to_csv(OUT_DIR / "scenario_assumptions.csv", index=False)
print(f"scenario_assumptions: {len(scenario_df)} rows")

# ---------------------------------------------------------------------
# 4. ML risk training data — a LARGER, independently generated synthetic
#    set of already-computed KPI feature vectors + a rule-based risk
#    label. Not used by the current phase (no ML endpoint is being
#    built yet), but prepared now so a future ML phase has ready,
#    documented training data rather than needing to build this later.
#
#    Labelling rule (rule-based, since no real labelled SME risk dataset
#    exists for a student project — documented here, not hidden):
#      risk_score = weighted combination of margin, liquidity, leverage,
#      and cash-flow health (same shape as the Financial Health Score),
#      then banded into Low / Medium / High.
# ---------------------------------------------------------------------
N_ML_ROWS = 600
ml_rows = []
for i in range(N_ML_ROWS):
    net_margin = RNG.normal(0.06, 0.09)
    operating_margin = net_margin + RNG.normal(0.03, 0.03)
    gross_margin = operating_margin + RNG.uniform(0.05, 0.25)
    current_ratio = max(0.2, RNG.normal(1.4, 0.55))
    quick_ratio = max(0.1, current_ratio - RNG.uniform(0.2, 0.6))
    debt_to_equity = max(0.0, RNG.normal(1.0, 0.7))
    interest_coverage = max(-5.0, RNG.normal(4.0, 4.5))
    operating_cash_flow_margin = net_margin + RNG.normal(0.02, 0.05)
    revenue_growth = RNG.normal(0.03, 0.12)

    # Rule-based labelling (same normalization spirit as the Financial
    # Health Score — documented, deterministic, not learned).
    def norm(value, low, high):
        return float(np.clip((value - low) / (high - low), 0.0, 1.0))

    profitability = np.mean([
        norm(net_margin, 0.0, 0.20),
        norm(operating_margin, 0.0, 0.25),
        norm(gross_margin, 0.10, 0.60),
    ])
    liquidity = np.mean([
        norm(current_ratio, 0.5, 2.5),
        norm(quick_ratio, 0.3, 1.5),
    ])
    leverage = np.mean([
        norm(3.0 - debt_to_equity, 0.0, 3.0),
        norm(interest_coverage, 0.0, 10.0),
    ])
    cash_flow = norm(operating_cash_flow_margin, -0.05, 0.20)

    composite = 0.30 * profitability + 0.25 * liquidity + 0.25 * leverage + 0.20 * cash_flow
    composite_score = composite * 100

    if composite_score >= 65:
        risk_label = "Low"
    elif composite_score >= 40:
        risk_label = "Medium"
    else:
        risk_label = "High"

    ml_rows.append({
        "sample_id": f"S{i+1:04d}",
        "net_margin": round(net_margin, 4),
        "operating_margin": round(operating_margin, 4),
        "gross_margin": round(gross_margin, 4),
        "current_ratio": round(current_ratio, 3),
        "quick_ratio": round(quick_ratio, 3),
        "debt_to_equity": round(debt_to_equity, 3),
        "interest_coverage": round(interest_coverage, 3),
        "operating_cash_flow_margin": round(operating_cash_flow_margin, 4),
        "revenue_growth": round(revenue_growth, 4),
        "composite_health_score": round(composite_score, 2),
        "risk_label": risk_label,
    })

ml_df = pd.DataFrame(ml_rows)
ml_df.to_csv(OUT_DIR / "ml_risk_training.csv", index=False)
print(f"ml_risk_training: {len(ml_df)} rows, label distribution:\n{ml_df['risk_label'].value_counts()}")

print("\nAll data files generated successfully in", OUT_DIR)
