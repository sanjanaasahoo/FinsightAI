"""
Tests for app/services/impact_engine.py.

Includes two REGRESSION tests (test_adverse_scenario_never_improves_*)
that encode bugs actually found while hand-verifying this module against
the real demo dataset during development:

  1. The original operating-cash-flow approximation scaled OCF by the
     ratio scenario_net_income / base_net_income. When base net income
     was negative (a loss-making period), that ratio could flip sign and
     inflate OCF instead of shrinking it — making an interest-rate HIKE
     appear to IMPROVE the Health Score. Fixed by switching to an
     additive dollar-delta approximation (see impact_engine.py).
  2. The original "most affected metrics" ranking used raw percentage
     change, which explodes (or flips sign) when a KPI's base value is
     near zero (e.g. a net margin hovering around 0%) — e.g. a real
     demo-data case produced a reported "+1436%" change from a tiny
     absolute move. Fixed by ranking KPIs on their bounded 0-100
     Health-Score normalized-score delta instead, and line items on
     dollar-change-as-%-of-revenue instead of %-of-own-base.
"""

from pathlib import Path

import pandas as pd
import pytest

from app.services.impact_engine import compute_business_impact
from app.services.scenario_engine import apply_combined_stress, apply_scenario

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

BASE_STATEMENT = {
    "revenue": 10_000_000.0,
    "cogs": 6_000_000.0,
    "operating_expenses": 2_000_000.0,
    "interest_expense": 400_000.0,
    "net_income": 900_000.0,  # not actually used by impact_engine — it derives net_income itself
    "current_assets": 4_000_000.0,
    "current_liabilities": 2_000_000.0,
    "inventory": 800_000.0,
    "total_debt": 5_000_000.0,
    "total_equity": 8_000_000.0,
    "cash_and_equivalents": 1_500_000.0,
    "operating_cash_flow": 1_200_000.0,
}

COMPANY = {
    "oil_energy_exposure_pct": 0.40,
    "import_cost_exposure_pct": 0.30,
    "export_revenue_exposure_pct": 0.25,
    "fx_debt_exposure_pct": 0.20,
    "variable_rate_debt_pct": 0.50,
    "demand_sensitivity_index": 1.1,
    "variable_cost_ratio": 0.65,
}

ALL_SCENARIOS = [
    ("oil_price_shock", 0.20),
    ("currency_depreciation", 0.10),
    ("interest_rate_hike", 0.02),
    ("demand_slowdown", -0.15),
]

# oil_price_shock, interest_rate_hike, and demand_slowdown are cost-side
# or revenue-only shocks with no mechanism that can ever improve
# profitability — every company should be flat-to-worse under them.
#
# currency_depreciation is DIFFERENT: it raises import-exposed costs AND
# raises export-exposed revenue. Whether that nets out adverse or
# favourable depends on the company's specific exposure profile — a
# genuine net exporter (large export-revenue exposure relative to its
# import-cost and FX-debt exposure, in dollar terms) can come out ahead.
# The test suite reflects that nuance rather than asserting a universal
# direction that wouldn't actually hold economically.
UNAMBIGUOUSLY_ADVERSE_SCENARIOS = [
    ("oil_price_shock", 0.20),
    ("interest_rate_hike", 0.02),
    ("demand_slowdown", -0.15),
]


def test_impact_structure_has_expected_keys():
    scenario_stmt = apply_scenario(BASE_STATEMENT, COMPANY, "oil_price_shock", 0.20)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)

    assert set(impact.keys()) == {
        "base", "scenario", "kpi_comparison", "line_item_comparison",
        "health_score_change", "most_affected_metrics",
    }
    assert "health_score" in impact["base"]
    assert "health_score" in impact["scenario"]


@pytest.mark.parametrize("scenario_type,magnitude", UNAMBIGUOUSLY_ADVERSE_SCENARIOS)
def test_adverse_scenario_never_improves_health_score_on_a_healthy_company(scenario_type, magnitude):
    """Regression test for the cash-flow-scaling sign-flip bug (see module docstring, bug #1)."""
    scenario_stmt = apply_scenario(BASE_STATEMENT, COMPANY, scenario_type, magnitude)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)
    assert impact["health_score_change"] <= 0.01, (
        f"{scenario_type} should never IMPROVE the Health Score, "
        f"got a change of {impact['health_score_change']}"
    )


def test_currency_depreciation_hurts_a_net_importer():
    """A company with import/FX-debt exposure but negligible export exposure should get worse."""
    net_importer = dict(COMPANY)
    net_importer["import_cost_exposure_pct"] = 0.50
    net_importer["export_revenue_exposure_pct"] = 0.02
    net_importer["fx_debt_exposure_pct"] = 0.30

    scenario_stmt = apply_scenario(BASE_STATEMENT, net_importer, "currency_depreciation", 0.10)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)
    assert impact["health_score_change"] <= 0.01


def test_currency_depreciation_can_help_a_net_exporter():
    """
    A company with large export exposure and minimal import/FX-debt
    exposure can genuinely come out ahead under depreciation — this is
    correct behaviour, not a bug, and is why currency_depreciation is
    excluded from the "always adverse" regression test above.
    """
    net_exporter = dict(COMPANY)
    net_exporter["export_revenue_exposure_pct"] = 0.60
    net_exporter["import_cost_exposure_pct"] = 0.02
    net_exporter["fx_debt_exposure_pct"] = 0.02

    scenario_stmt = apply_scenario(BASE_STATEMENT, net_exporter, "currency_depreciation", 0.10)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)
    assert impact["health_score_change"] > 0


def test_combined_stress_never_improves_health_score():
    scenario_stmt = apply_combined_stress(BASE_STATEMENT, COMPANY)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)
    assert impact["health_score_change"] <= 0.01


def test_adverse_scenario_never_improves_health_score_on_the_full_demo_dataset():
    """
    Same regression check as above, but sweeping every (company, period,
    scenario) combination in the real 160-row demo dataset — this is what
    actually caught bug #1 originally (a specific C001 2024-Q4 row).
    """
    df = pd.read_csv(DATA_DIR / "company_financials.csv")
    exposure_fields = list(COMPANY.keys())

    violations = []
    for _, row in df.iterrows():
        statement = row.to_dict()
        company = {k: row[k] for k in exposure_fields}

        for scenario_type, magnitude in UNAMBIGUOUSLY_ADVERSE_SCENARIOS:
            scenario_stmt = apply_scenario(statement, company, scenario_type, magnitude)
            impact = compute_business_impact(statement, scenario_stmt)
            if impact["health_score_change"] > 0.01:
                violations.append((row["company_id"], row["period_label"], scenario_type,
                                    impact["health_score_change"]))

    assert violations == [], f"Found {len(violations)} cases where an adverse scenario improved the score: {violations[:5]}"


def test_most_affected_ranking_is_bounded_not_exploding_pct_change():
    """
    Regression test for the near-zero-base ranking bug (bug #2). Construct
    a statement where net income sits very close to zero, so a raw
    percentage-change ranking would blow up; confirm the actual ranking
    values stay in a sane, bounded range instead.
    """
    near_zero_margin_statement = dict(BASE_STATEMENT)
    # Engineer cogs/opex so net income (derived internally) lands near zero.
    near_zero_margin_statement["cogs"] = 7_450_000.0
    near_zero_margin_statement["operating_expenses"] = 2_000_000.0

    scenario_stmt = apply_scenario(near_zero_margin_statement, COMPANY, "oil_price_shock", 0.20)
    impact = compute_business_impact(near_zero_margin_statement, scenario_stmt)

    for entry in impact["most_affected_metrics"]:
        assert abs(entry["ranking_value"]) <= 100.5, (
            f"ranking_value for {entry['metric']} exploded to {entry['ranking_value']} "
            f"— the near-zero-base ranking bug may have regressed"
        )


def test_most_affected_metrics_are_sorted_descending_by_magnitude():
    scenario_stmt = apply_combined_stress(BASE_STATEMENT, COMPANY)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)

    magnitudes = [abs(m["ranking_value"]) for m in impact["most_affected_metrics"]]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_kpi_comparison_reports_base_and_scenario_values():
    scenario_stmt = apply_scenario(BASE_STATEMENT, COMPANY, "demand_slowdown", -0.15)
    impact = compute_business_impact(BASE_STATEMENT, scenario_stmt)

    revenue_growth_not_present = "revenue_growth" not in impact["kpi_comparison"]
    assert revenue_growth_not_present  # excluded deliberately — see impact_engine.py docstring

    net_margin_comparison = impact["kpi_comparison"]["net_margin"]
    assert net_margin_comparison["scenario"] < net_margin_comparison["base"]
