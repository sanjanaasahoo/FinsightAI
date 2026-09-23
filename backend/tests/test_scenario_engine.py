"""
Tests for app/services/scenario_engine.py.

Every scenario formula is checked against its exact documented formula
(scenario_assumptions.py), computed independently in this test file — not
by re-importing and trusting the engine's own arithmetic.
"""

import pytest

from app.services.scenario_engine import (
    apply_combined_stress,
    apply_currency_depreciation,
    apply_demand_slowdown,
    apply_interest_rate_hike,
    apply_oil_price_shock,
    apply_scenario,
)

BASE_STATEMENT = {
    "revenue": 10_000_000.0,
    "cogs": 6_000_000.0,
    "operating_expenses": 2_000_000.0,
    "interest_expense": 400_000.0,
    "net_income": 900_000.0,
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


def test_oil_price_shock_only_touches_cogs():
    result = apply_oil_price_shock(BASE_STATEMENT, COMPANY, magnitude=0.20)
    expected_cogs = BASE_STATEMENT["cogs"] * (1 + 0.40 * 0.20)
    assert result["cogs"] == pytest.approx(expected_cogs)
    assert result["revenue"] == BASE_STATEMENT["revenue"]
    assert result["interest_expense"] == BASE_STATEMENT["interest_expense"]


def test_currency_depreciation_touches_cogs_revenue_and_interest():
    result = apply_currency_depreciation(BASE_STATEMENT, COMPANY, magnitude=0.10)
    assert result["cogs"] == pytest.approx(BASE_STATEMENT["cogs"] * (1 + 0.30 * 0.10))
    assert result["revenue"] == pytest.approx(BASE_STATEMENT["revenue"] * (1 + 0.25 * 0.10))
    assert result["interest_expense"] == pytest.approx(
        BASE_STATEMENT["interest_expense"] * (1 + 0.20 * 0.10)
    )


def test_interest_rate_hike_only_touches_interest_expense():
    result = apply_interest_rate_hike(BASE_STATEMENT, COMPANY, magnitude=0.02)
    expected_interest = BASE_STATEMENT["interest_expense"] + (
        BASE_STATEMENT["total_debt"] * 0.50 * 0.02
    )
    assert result["interest_expense"] == pytest.approx(expected_interest)
    assert result["revenue"] == BASE_STATEMENT["revenue"]
    assert result["cogs"] == BASE_STATEMENT["cogs"]


def test_demand_slowdown_shrinks_revenue_more_than_cogs():
    result = apply_demand_slowdown(BASE_STATEMENT, COMPANY, magnitude=-0.15)
    expected_revenue = BASE_STATEMENT["revenue"] * (1 + -0.15 * 1.1)
    expected_cogs = BASE_STATEMENT["cogs"] * (1 + -0.15 * 1.1 * 0.65)
    assert result["revenue"] == pytest.approx(expected_revenue)
    assert result["cogs"] == pytest.approx(expected_cogs)

    revenue_pct_drop = 1 - result["revenue"] / BASE_STATEMENT["revenue"]
    cogs_pct_drop = 1 - result["cogs"] / BASE_STATEMENT["cogs"]
    assert revenue_pct_drop > cogs_pct_drop  # fixed costs cushion COGS's decline


def test_apply_scenario_rejects_unknown_type():
    with pytest.raises(ValueError):
        apply_scenario(BASE_STATEMENT, COMPANY, "meteor_strike", 0.5)


def test_apply_scenario_rejects_combined_stress_directly():
    """combined_stress must go through apply_combined_stress(), not apply_scenario()."""
    with pytest.raises(ValueError):
        apply_scenario(BASE_STATEMENT, COMPANY, "combined_stress", 0.5)


def test_combined_stress_is_additive_not_compounded():
    """
    The combined result must equal the base case plus the SUM of each
    individual scenario's independent dollar delta — never the result of
    chaining scenarios sequentially (which would compound and depend on
    order). This is the core documented assumption for combined_stress.
    """
    oil = apply_oil_price_shock(BASE_STATEMENT, COMPANY, 0.20)
    fx = apply_currency_depreciation(BASE_STATEMENT, COMPANY, 0.10)
    demand = apply_demand_slowdown(BASE_STATEMENT, COMPANY, -0.15)
    rate = apply_interest_rate_hike(BASE_STATEMENT, COMPANY, 0.02)

    combined = apply_combined_stress(BASE_STATEMENT, COMPANY)

    expected_cogs = BASE_STATEMENT["cogs"] + sum(
        s["cogs"] - BASE_STATEMENT["cogs"] for s in (oil, fx, demand)
    )
    expected_revenue = BASE_STATEMENT["revenue"] + sum(
        s["revenue"] - BASE_STATEMENT["revenue"] for s in (fx, demand)
    )
    expected_interest = BASE_STATEMENT["interest_expense"] + sum(
        s["interest_expense"] - BASE_STATEMENT["interest_expense"] for s in (fx, rate)
    )

    assert combined["cogs"] == pytest.approx(expected_cogs)
    assert combined["revenue"] == pytest.approx(expected_revenue)
    assert combined["interest_expense"] == pytest.approx(expected_interest)


def test_combined_stress_respects_magnitude_overrides():
    combined_default = apply_combined_stress(BASE_STATEMENT, COMPANY)
    combined_bigger_oil_shock = apply_combined_stress(
        BASE_STATEMENT, COMPANY, magnitudes={"oil_price_shock": 0.50}
    )
    # A bigger oil shock should push COGS higher than the default-magnitude run.
    assert combined_bigger_oil_shock["cogs"] > combined_default["cogs"]


def test_zero_exposure_means_zero_impact():
    """A company with 0% exposure on every field should be completely unaffected."""
    zero_exposure_company = {k: 0.0 for k in COMPANY}
    zero_exposure_company["demand_sensitivity_index"] = 0.0
    zero_exposure_company["variable_cost_ratio"] = 0.0

    for scenario_type, magnitude in [
        ("oil_price_shock", 0.20),
        ("currency_depreciation", 0.10),
        ("interest_rate_hike", 0.02),
        ("demand_slowdown", -0.15),
    ]:
        result = apply_scenario(BASE_STATEMENT, zero_exposure_company, scenario_type, magnitude)
        assert result["revenue"] == BASE_STATEMENT["revenue"]
        assert result["cogs"] == BASE_STATEMENT["cogs"]
        assert result["interest_expense"] == BASE_STATEMENT["interest_expense"]
