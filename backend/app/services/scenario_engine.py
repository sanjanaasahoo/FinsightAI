"""
Scenario Simulation Engine.

Applies each documented scenario (see scenario_assumptions.py) to a BASE
financial statement, using the company's own exposure fields to drive the
size of the adjustment — not a flat, company-agnostic KPI tweak.

Every function here is a pure transformation:
    (base_statement: dict, company_exposures: dict, magnitude: float) -> scenario_statement: dict

This is what makes each scenario independently unit-testable against
hand-calculated expected values (see tests/test_scenario_engine.py), and
what guarantees the scenario case is computed with exactly the same
downstream KPI/Health-Score logic as the base case: the caller re-runs
`analytics_engine.compute_kpis()` on the OUTPUT of these functions, the
same way it does for the base statement.

No ML, no LLM, no randomness anywhere in this module.
"""

from typing import Dict

from app.services.scenario_assumptions import (
    COMBINED_SCENARIO_TYPE,
    INDIVIDUAL_SCENARIO_TYPES,
    get_default_magnitudes_for_combined,
)


def _copy_statement(statement: Dict) -> Dict:
    """Shallow copy is enough — statement values are all scalars."""
    return dict(statement)


def apply_oil_price_shock(statement: Dict, company: Dict, magnitude: float) -> Dict:
    """
    oil_price_shock: raises COGS in proportion to the company's
    oil/energy cost exposure.

        cogs_scenario = cogs_base * (1 + oil_energy_exposure_pct * magnitude)
    """
    scenario = _copy_statement(statement)
    exposure = company["oil_energy_exposure_pct"]
    scenario["cogs"] = statement["cogs"] * (1 + exposure * magnitude)
    return scenario


def apply_currency_depreciation(statement: Dict, company: Dict, magnitude: float) -> Dict:
    """
    currency_depreciation: raises import-exposed COGS, raises
    export-exposed revenue, raises FX-debt-exposed interest expense.

        cogs_scenario = cogs_base * (1 + import_cost_exposure_pct * magnitude)
        revenue_scenario = revenue_base * (1 + export_revenue_exposure_pct * magnitude)
        interest_expense_scenario = interest_expense_base * (1 + fx_debt_exposure_pct * magnitude)
    """
    scenario = _copy_statement(statement)
    scenario["cogs"] = statement["cogs"] * (1 + company["import_cost_exposure_pct"] * magnitude)
    scenario["revenue"] = statement["revenue"] * (1 + company["export_revenue_exposure_pct"] * magnitude)
    scenario["interest_expense"] = statement["interest_expense"] * (
        1 + company["fx_debt_exposure_pct"] * magnitude
    )
    return scenario


def apply_interest_rate_hike(statement: Dict, company: Dict, magnitude: float) -> Dict:
    """
    interest_rate_hike: only the variable-rate share of total debt
    reprices at the new rate delta.

        interest_expense_scenario = interest_expense_base
                                     + (total_debt_base * variable_rate_debt_pct * magnitude)
    """
    scenario = _copy_statement(statement)
    additional_interest = statement["total_debt"] * company["variable_rate_debt_pct"] * magnitude
    scenario["interest_expense"] = statement["interest_expense"] + additional_interest
    return scenario


def apply_demand_slowdown(statement: Dict, company: Dict, magnitude: float) -> Dict:
    """
    demand_slowdown: revenue falls by the shock scaled by the company's
    demand sensitivity; COGS falls by less, since only the variable-cost
    share shrinks with volume.

        revenue_scenario = revenue_base * (1 + magnitude * demand_sensitivity_index)
        cogs_scenario = cogs_base * (1 + magnitude * demand_sensitivity_index * variable_cost_ratio)
    """
    scenario = _copy_statement(statement)
    sensitivity = company["demand_sensitivity_index"]
    scenario["revenue"] = statement["revenue"] * (1 + magnitude * sensitivity)
    scenario["cogs"] = statement["cogs"] * (1 + magnitude * sensitivity * company["variable_cost_ratio"])
    return scenario


_SCENARIO_FUNCTIONS = {
    "oil_price_shock": apply_oil_price_shock,
    "currency_depreciation": apply_currency_depreciation,
    "interest_rate_hike": apply_interest_rate_hike,
    "demand_slowdown": apply_demand_slowdown,
}


def apply_scenario(statement: Dict, company: Dict, scenario_type: str, magnitude: float) -> Dict:
    """
    Apply a single named scenario to a base statement. Raises ValueError
    for an unrecognized scenario_type or for `combined_stress` (which
    must go through apply_combined_stress instead, since it needs a
    magnitude per sub-scenario, not one single magnitude).
    """
    if scenario_type == COMBINED_SCENARIO_TYPE:
        raise ValueError(
            "combined_stress must be applied via apply_combined_stress(), "
            "which takes a magnitude per sub-scenario."
        )
    if scenario_type not in _SCENARIO_FUNCTIONS:
        raise ValueError(f"Unknown scenario_type: {scenario_type}")

    return _SCENARIO_FUNCTIONS[scenario_type](statement, company, magnitude)


def apply_combined_stress(statement: Dict, company: Dict, magnitudes: Dict[str, float] = None) -> Dict:
    """
    combined_stress: apply all four individual scenarios to the SAME base
    case independently, then sum each one's dollar-impact (scenario -
    base, per affected field) onto the base case.

    This is deliberately ADDITIVE rather than sequential/compounded — see
    scenario_assumptions.py's `combined_stress` rationale for why.

    Args:
        magnitudes: optional dict of {scenario_type: magnitude}. Any
            scenario type omitted uses its documented default. If None,
            all four defaults are used.
    """
    effective_magnitudes = get_default_magnitudes_for_combined()
    if magnitudes:
        effective_magnitudes.update(magnitudes)

    combined = _copy_statement(statement)
    # Track the cumulative delta per field, computed independently against
    # the ORIGINAL base statement (not against each other), then applied
    # once at the end — this is what "additive, not compounded" means.
    deltas = {"revenue": 0.0, "cogs": 0.0, "interest_expense": 0.0}

    for scenario_type in INDIVIDUAL_SCENARIO_TYPES:
        magnitude = effective_magnitudes[scenario_type]
        scenario_result = _SCENARIO_FUNCTIONS[scenario_type](statement, company, magnitude)
        for field in deltas:
            deltas[field] += scenario_result[field] - statement[field]

    for field, delta in deltas.items():
        combined[field] = statement[field] + delta

    return combined
