"""
Business Impact Engine.

Given a BASE statement and a SCENARIO statement (already produced by
scenario_engine.py), this module:
  1. Re-runs the exact same Financial Analytics Engine logic
     (analytics_engine.compute_kpis / compute_health_score) on both, so
     base and scenario are computed identically — only the input differs.
  2. Diffs every KPI and the Health Score, base vs scenario.
  3. Ranks the most-affected metrics by absolute percentage change.

Kept as its own module (separate from scenario_engine.py) so a future
scenario type can reuse this same comparison logic without duplicating
it — see architecture document's "Business Impact Engine" design note.

No ML, no LLM, no randomness anywhere in this module.
"""

import math
from typing import Dict, List, Optional

from app.services.analytics_engine import compute_health_score, compute_kpis, normalize_metric

# KPIs to compare/rank. revenue_growth is excluded — it depends on a PRIOR
# period, which is a base-case-only concept; comparing it base vs scenario
# (same period, no separate prior scenario period) isn't meaningful.
_COMPARABLE_KPIS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "current_ratio",
    "quick_ratio",
    "debt_to_equity",
    "interest_coverage",
    "operating_cash_flow_margin",
]

# Raw line items worth showing base-vs-scenario even though they aren't
# ratios (revenue/cost/profit/cash-flow-related, per the brief).
_COMPARABLE_LINE_ITEMS = [
    "revenue",
    "cogs",
    "operating_expenses",
    "interest_expense",
    "net_income",
    "operating_cash_flow",
]


def _pct_change(base: Optional[float], scenario: Optional[float]) -> Optional[float]:
    if base is None or scenario is None or math.isclose(base, 0.0, abs_tol=1e-9):
        return None
    return (scenario - base) / abs(base)


def _derive_line_items(statement: Dict) -> Dict:
    """
    Derive net_income for a scenario statement, since scenario_engine.py
    only adjusts revenue/cogs/interest_expense directly — net_income must
    be recomputed downstream using the same tax-effect logic as the rest
    of the platform assumes (operating income flows to pretax income,
    taxed at a flat, documented rate).
    """
    gross_profit = statement["revenue"] - statement["cogs"]
    operating_income = gross_profit - statement["operating_expenses"]
    pretax_income = operating_income - statement["interest_expense"]

    tax_rate = 0.25  # documented flat assumption, consistent with the demo dataset
    net_income = pretax_income * (1 - tax_rate) if pretax_income > 0 else pretax_income

    result = dict(statement)
    result["net_income"] = net_income
    return result


def compute_business_impact(base_statement: Dict, scenario_statement: Dict) -> Dict:
    """
    Compare a base statement against its scenario-adjusted counterpart.

    Both statements are expected to already reflect the scenario's
    adjustments to revenue/cogs/interest_expense (i.e. scenario_statement
    is the output of scenario_engine.apply_scenario /
    apply_combined_stress). This function derives net_income
    consistently for both, computes KPIs + Health Score for both via the
    same Financial Analytics Engine, and returns the full comparison.
    """
    base_full = _derive_line_items(base_statement)
    scenario_full = _derive_line_items(scenario_statement)

    # Operating cash flow isn't directly touched by any scenario. We
    # assume it moves dollar-for-dollar with the change in net income —
    # i.e. non-cash add-backs (depreciation) and working-capital effects
    # are held constant under the scenario, and only the profit impact
    # flows through to cash. This is an explicit, documented
    # simplification (not a measured cash-flow model), chosen specifically
    # because it stays well-behaved (monotonic, no sign flips or
    # divide-by-near-zero blowups) even when net income is negative or
    # close to zero — a ratio-based scaling does not have that property.
    net_income_delta = scenario_full["net_income"] - base_full["net_income"]
    scenario_full["operating_cash_flow"] = base_full["operating_cash_flow"] + net_income_delta

    base_kpis = compute_kpis(base_full, previous_statement=None)
    scenario_kpis = compute_kpis(scenario_full, previous_statement=None)

    base_health_score, base_breakdown = compute_health_score(base_kpis)
    scenario_health_score, scenario_breakdown = compute_health_score(scenario_kpis)

    kpi_comparison = {}
    for kpi_name in _COMPARABLE_KPIS:
        base_value = base_kpis.get(kpi_name)
        scenario_value = scenario_kpis.get(kpi_name)
        kpi_comparison[kpi_name] = {
            "base": base_value,
            "scenario": scenario_value,
            "absolute_change": (
                None if base_value is None or scenario_value is None
                else scenario_value - base_value
            ),
            "pct_change": _pct_change(base_value, scenario_value),
        }

    line_item_comparison = {}
    for field in _COMPARABLE_LINE_ITEMS:
        base_value = base_full.get(field)
        scenario_value = scenario_full.get(field)
        line_item_comparison[field] = {
            "base": base_value,
            "scenario": scenario_value,
            "absolute_change": (
                None if base_value is None or scenario_value is None
                else scenario_value - base_value
            ),
            "pct_change": _pct_change(base_value, scenario_value),
        }

    most_affected = _rank_most_affected(
        kpi_comparison, line_item_comparison, base_kpis, scenario_kpis, base_full["revenue"]
    )

    return {
        "base": {
            "kpis": base_kpis,
            "health_score": base_health_score,
            "health_score_breakdown": base_breakdown,
        },
        "scenario": {
            "kpis": scenario_kpis,
            "health_score": scenario_health_score,
            "health_score_breakdown": scenario_breakdown,
        },
        "kpi_comparison": kpi_comparison,
        "line_item_comparison": line_item_comparison,
        "health_score_change": round(scenario_health_score - base_health_score, 2),
        "most_affected_metrics": most_affected,
    }


def _rank_most_affected(
    kpi_comparison: Dict,
    line_item_comparison: Dict,
    base_kpis: Dict,
    scenario_kpis: Dict,
    base_revenue: float,
    top_n: int = 5,
) -> List[Dict]:
    """
    Rank compared metrics by how much they moved, using two DIFFERENT
    (and deliberately NOT percentage-of-own-base) measures:

    - KPIs: ranked by the absolute change in their 0-100 Health-Score
      normalized_score. This is what "most affected" should mean for a
      ratio — how much did this metric's contribution to financial
      health move — and it stays well-behaved even when the KPI's own
      raw value is near zero (e.g. a net margin hovering around 0%),
      where a raw percentage change would blow up or flip sign for a
      tiny absolute move.
    - Line items (revenue/cogs/opex/interest/net income/cash flow):
      ranked by the dollar change EXPRESSED AS A % OF BASE REVENUE, not
      as a % of the line item's own base value — this avoids the same
      near-zero-base instability for a line item like net_income that
      can sit close to $0, and is also a standard, easily-defended way
      to express financial impact ("this scenario cost 2.1% of revenue").
    """
    candidates = []

    for name, comparison in kpi_comparison.items():
        base_value = base_kpis.get(name)
        scenario_value = scenario_kpis.get(name)
        normalized_change = normalize_metric(name, scenario_value) - normalize_metric(name, base_value)
        candidates.append({
            "metric": name,
            "metric_kind": "kpi",
            "ranking_measure": "health_score_points_change",
            "ranking_value": round(normalized_change, 2),
            "absolute_change": comparison["absolute_change"],
            "pct_change": comparison["pct_change"],
        })

    revenue_denominator = base_revenue if not math.isclose(base_revenue, 0.0, abs_tol=1e-9) else None
    for name, comparison in line_item_comparison.items():
        absolute_change = comparison["absolute_change"]
        pct_of_revenue = (
            None if absolute_change is None or revenue_denominator is None
            else absolute_change / revenue_denominator
        )
        candidates.append({
            "metric": name,
            "metric_kind": "line_item",
            "ranking_measure": "pct_of_base_revenue",
            "ranking_value": None if pct_of_revenue is None else round(pct_of_revenue * 100, 2),
            "absolute_change": absolute_change,
            "pct_change": comparison["pct_change"],
        })

    ranked = [c for c in candidates if c["ranking_value"] is not None]
    ranked.sort(key=lambda c: abs(c["ranking_value"]), reverse=True)
    return ranked[:top_n]
