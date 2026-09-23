"""
Financial Analytics Engine.

Pure, deterministic functions that turn a single financial statement
(plus, optionally, the prior period's statement) into:
  - a dict of standard financial KPIs/ratios
  - a 0-100 Financial Health Score with a fully itemized component
    breakdown (so every point of the score is traceable to a specific
    sub-metric — no black box)
  - period-over-period trend analysis across a company's statements

Deliberately has ZERO dependency on FastAPI, SQLAlchemy, or any ORM
model — every function here takes and returns plain dicts/floats. This
is what makes the engine trivially unit-testable (see
tests/test_analytics_engine.py) and is also what the Scenario Simulation
Engine reuses to compute scenario-case KPIs with exactly the same logic
as the base case (see scenario_engine.py / impact_engine.py).

No LLM, no ML, and no randomness anywhere in this module.
"""

import math
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------
# KPI computation
# ---------------------------------------------------------------------

# Fields a "statement" dict must contain to compute KPIs. Kept as a
# module-level constant so validation_service.py and tests can both
# reference the same list.
REQUIRED_STATEMENT_FIELDS = [
    "revenue",
    "cogs",
    "operating_expenses",
    "interest_expense",
    "net_income",
    "current_assets",
    "current_liabilities",
    "inventory",
    "total_debt",
    "total_equity",
    "cash_and_equivalents",
    "operating_cash_flow",
]


def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
    """Return numerator/denominator, or None if the denominator is ~0."""
    if denominator is None or math.isclose(denominator, 0.0, abs_tol=1e-9):
        return None
    return numerator / denominator


def compute_kpis(statement: Dict, previous_statement: Optional[Dict] = None) -> Dict[str, Optional[float]]:
    """
    Compute all financial KPIs/ratios for a single statement.

    Args:
        statement: dict with the REQUIRED_STATEMENT_FIELDS keys (values in
            the reporting currency, e.g. USD).
        previous_statement: the prior period's statement dict, used only
            for Revenue Growth. If None, revenue_growth is returned as None
            (the very first period for a company has no growth figure).

    Returns:
        A dict of KPI name -> float (or None where undefined, e.g.
        interest_coverage when interest_expense is 0).
    """
    revenue = statement["revenue"]
    cogs = statement["cogs"]
    operating_expenses = statement["operating_expenses"]
    interest_expense = statement["interest_expense"]
    net_income = statement["net_income"]
    current_assets = statement["current_assets"]
    current_liabilities = statement["current_liabilities"]
    inventory = statement["inventory"]
    total_debt = statement["total_debt"]
    total_equity = statement["total_equity"]
    operating_cash_flow = statement["operating_cash_flow"]

    gross_profit = revenue - cogs
    operating_income = gross_profit - operating_expenses

    revenue_growth = None
    if previous_statement is not None:
        prev_revenue = previous_statement["revenue"]
        revenue_growth = _safe_divide(revenue - prev_revenue, prev_revenue)

    kpis = {
        "revenue_growth": revenue_growth,
        "gross_margin": _safe_divide(gross_profit, revenue),
        "operating_margin": _safe_divide(operating_income, revenue),
        "net_margin": _safe_divide(net_income, revenue),
        "current_ratio": _safe_divide(current_assets, current_liabilities),
        "quick_ratio": _safe_divide(current_assets - inventory, current_liabilities),
        "debt_to_equity": _safe_divide(total_debt, total_equity),
        "interest_coverage": _safe_divide(operating_income, interest_expense),
        "operating_cash_flow_margin": _safe_divide(operating_cash_flow, revenue),
    }
    return kpis


# ---------------------------------------------------------------------
# Financial Health Score
# ---------------------------------------------------------------------

# Documented normalization bands: (metric_name -> (low, high, higher_is_better)).
# A value at/below `low` normalizes to 0; at/above `high` normalizes to 100;
# linearly interpolated in between. These bands are fixed, human-chosen
# constants (NOT learned from data) so the score stays fully deterministic
# and explainable — "why did the score drop" always has a concrete answer.
_NORMALIZATION_BANDS: Dict[str, Tuple[float, float, bool]] = {
    "net_margin": (0.00, 0.20, True),
    "operating_margin": (0.00, 0.25, True),
    "gross_margin": (0.10, 0.60, True),
    "current_ratio": (0.5, 2.5, True),
    "quick_ratio": (0.3, 1.5, True),
    "debt_to_equity": (0.0, 3.0, False),  # lower is better
    "interest_coverage": (0.0, 10.0, True),
    "operating_cash_flow_margin": (-0.05, 0.20, True),
}

# Component weights (must sum to 1.0). Fixed, documented constants.
_COMPONENT_WEIGHTS = {
    "profitability": 0.30,
    "liquidity": 0.25,
    "leverage": 0.25,
    "cash_flow": 0.20,
}

_COMPONENT_METRICS = {
    "profitability": ["net_margin", "operating_margin", "gross_margin"],
    "liquidity": ["current_ratio", "quick_ratio"],
    "leverage": ["debt_to_equity", "interest_coverage"],
    "cash_flow": ["operating_cash_flow_margin"],
}


def normalize_metric(metric_name: str, value: Optional[float]) -> float:
    """
    Normalize a single KPI value to a 0-100 sub-score using its documented
    band. A None value (undefined ratio, e.g. divide-by-zero) normalizes
    to 0 — treated as "unknown/unfavorable" rather than silently excluded,
    so a missing ratio can never inflate the score.
    """
    if value is None:
        return 0.0

    low, high, higher_is_better = _NORMALIZATION_BANDS[metric_name]

    if higher_is_better:
        normalized = (value - low) / (high - low)
    else:
        # Lower is better (e.g. debt_to_equity): flip the direction so the
        # same 0-100 clamp/interpolate logic applies either way.
        normalized = (high - value) / (high - low)

    return float(np.clip(normalized, 0.0, 1.0) * 100)


def compute_health_score(kpis: Dict[str, Optional[float]]) -> Tuple[float, Dict]:
    """
    Compute the 0-100 Financial Health Score and a full breakdown of how
    it was derived.

    Returns:
        (health_score, breakdown) where breakdown is:
        {
          "components": {
            "profitability": {
              "weight": 0.30,
              "metrics": {"net_margin": {"value": ..., "normalized_score": ...}, ...},
              "component_score": ...,       # 0-100, average of its metrics' normalized scores
              "weighted_contribution": ...  # component_score * weight
            },
            ...
          },
          "health_score": ...  # sum of weighted_contribution across all components
        }
    """
    components_breakdown = {}
    total_score = 0.0

    for component_name, metric_names in _COMPONENT_METRICS.items():
        metrics_breakdown = {}
        normalized_scores: List[float] = []

        for metric_name in metric_names:
            raw_value = kpis.get(metric_name)
            normalized_score = normalize_metric(metric_name, raw_value)
            metrics_breakdown[metric_name] = {
                "value": raw_value,
                "normalized_score": round(normalized_score, 2),
            }
            normalized_scores.append(normalized_score)

        component_score = float(np.mean(normalized_scores)) if normalized_scores else 0.0
        weight = _COMPONENT_WEIGHTS[component_name]
        weighted_contribution = component_score * weight

        components_breakdown[component_name] = {
            "weight": weight,
            "metrics": metrics_breakdown,
            "component_score": round(component_score, 2),
            "weighted_contribution": round(weighted_contribution, 2),
        }
        total_score += weighted_contribution

    health_score = round(float(np.clip(total_score, 0.0, 100.0)), 2)

    breakdown = {
        "components": components_breakdown,
        "health_score": health_score,
    }
    return health_score, breakdown


# ---------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------

_TREND_METRICS = [
    "revenue",
    "net_margin",
    "current_ratio",
    "debt_to_equity",
    "operating_cash_flow_margin",
]

_TREND_STABLE_THRESHOLD = 0.02  # slope magnitude below this (as a fraction of series mean) is "stable"


def compute_trend(periods: List[Dict]) -> Dict:
    """
    Compute period-over-period trend analysis across a company's
    chronologically-ordered statements.

    Args:
        periods: list of dicts, each with at minimum:
            {"period_label": str, "statement": {...raw fields...},
             "kpis": {...compute_kpis() output...}}
            ordered oldest -> newest.

    Returns:
        {
          "revenue": {
            "series": [{"period_label": ..., "value": ...}, ...],
            "period_over_period_pct_change": [None, 0.05, -0.02, ...],
            "direction": "improving" | "declining" | "stable" | "insufficient_data",
            "slope": <float, raw linear-fit slope> or None
          },
          ... one entry per tracked metric ...
        }
    """
    if len(periods) < 2:
        return {
            metric: {
                "series": [
                    {"period_label": p["period_label"], "value": _extract_metric_value(p, metric)}
                    for p in periods
                ],
                "period_over_period_pct_change": [None] * len(periods),
                "direction": "insufficient_data",
                "slope": None,
            }
            for metric in _TREND_METRICS
        }

    result = {}
    for metric in _TREND_METRICS:
        values = [_extract_metric_value(p, metric) for p in periods]
        series = [
            {"period_label": p["period_label"], "value": v}
            for p, v in zip(periods, values)
        ]

        pct_changes: List[Optional[float]] = [None]
        for i in range(1, len(values)):
            prev, curr = values[i - 1], values[i]
            if prev is None or curr is None or math.isclose(prev, 0.0, abs_tol=1e-9):
                pct_changes.append(None)
            else:
                pct_changes.append((curr - prev) / abs(prev))

        clean_values = [v for v in values if v is not None]
        if len(clean_values) < 2:
            direction, slope = "insufficient_data", None
        else:
            x = np.arange(len(clean_values))
            slope = float(np.polyfit(x, clean_values, 1)[0])
            series_mean = float(np.mean(np.abs(clean_values))) or 1.0
            normalized_slope = slope / series_mean
            if normalized_slope > _TREND_STABLE_THRESHOLD:
                direction = "improving"
            elif normalized_slope < -_TREND_STABLE_THRESHOLD:
                direction = "declining"
            else:
                direction = "stable"

        result[metric] = {
            "series": series,
            "period_over_period_pct_change": pct_changes,
            "direction": direction,
            "slope": slope,
        }

    return result


def _extract_metric_value(period: Dict, metric: str) -> Optional[float]:
    """revenue lives on the raw statement; everything else is a KPI."""
    if metric == "revenue":
        return period["statement"]["revenue"]
    return period["kpis"].get(metric)
