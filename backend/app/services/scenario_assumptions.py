"""
Scenario assumptions — documented, deterministic transmission rules.

This module is the single source of truth *executed* by the Scenario
Simulation Engine (app/services/scenario_engine.py). It must stay
consistent with the human-readable copy at `data/scenario_assumptions.csv`
— that CSV exists so the same assumptions can be read/quoted without
opening code, but this module is what actually runs.

Every scenario transforms the BASE financial statement using one or more
of the company's "exposure fields" (see data/DATA_DICTIONARY.md) rather
than applying a flat, company-agnostic adjustment to a final KPI. This is
the core design decision behind the Scenario Simulation Engine: the same
20% oil price shock hits a logistics company harder than an IT services
company, because their `oil_energy_exposure_pct` differs.

No business logic beyond these constants lives in this module — the
actual transformation functions live in scenario_engine.py.
"""

from dataclasses import dataclass
from typing import Dict, Union


@dataclass(frozen=True)
class ScenarioAssumption:
    scenario_type: str
    default_magnitude: float
    magnitude_meaning: str
    affected_line_items: str
    transmission_fields: str
    formula: str
    rationale: str


SCENARIO_ASSUMPTIONS: Dict[str, ScenarioAssumption] = {
    "oil_price_shock": ScenarioAssumption(
        scenario_type="oil_price_shock",
        default_magnitude=0.20,
        magnitude_meaning="relative increase in oil/energy prices (0.20 = +20%)",
        affected_line_items="cogs",
        transmission_fields="oil_energy_exposure_pct",
        formula="cogs_scenario = cogs_base * (1 + oil_energy_exposure_pct * magnitude)",
        rationale=(
            "Companies with higher energy/logistics content in COGS (transport, "
            "energy, construction) see a larger cost pass-through from an oil "
            "price spike than companies with low energy intensity (e.g. IT "
            "services)."
        ),
    ),
    "currency_depreciation": ScenarioAssumption(
        scenario_type="currency_depreciation",
        default_magnitude=0.10,
        magnitude_meaning="relative local-currency depreciation vs USD (0.10 = +10% weaker)",
        affected_line_items="cogs, revenue, interest_expense",
        transmission_fields=(
            "import_cost_exposure_pct, export_revenue_exposure_pct, fx_debt_exposure_pct"
        ),
        formula=(
            "cogs_scenario = cogs_base * (1 + import_cost_exposure_pct * magnitude); "
            "revenue_scenario = revenue_base * (1 + export_revenue_exposure_pct * magnitude); "
            "interest_expense_scenario = interest_expense_base * "
            "(1 + fx_debt_exposure_pct * magnitude)"
        ),
        rationale=(
            "Depreciation raises the local-currency cost of imported inputs and "
            "FX-denominated debt service, but raises the local-currency value of "
            "export revenue — the net effect depends on each company's specific "
            "import/export/FX-debt mix, not a single blanket adjustment."
        ),
    ),
    "interest_rate_hike": ScenarioAssumption(
        scenario_type="interest_rate_hike",
        default_magnitude=0.02,
        magnitude_meaning="absolute increase in interest rate, percentage points (0.02 = +2pp)",
        affected_line_items="interest_expense",
        transmission_fields="variable_rate_debt_pct",
        formula=(
            "interest_expense_scenario = interest_expense_base + "
            "(total_debt_base * variable_rate_debt_pct * magnitude)"
        ),
        rationale=(
            "Only the variable-rate portion of a company's debt reprices "
            "immediately when rates rise; fixed-rate debt is unaffected until "
            "it matures and is refinanced."
        ),
    ),
    "demand_slowdown": ScenarioAssumption(
        scenario_type="demand_slowdown",
        default_magnitude=-0.15,
        magnitude_meaning="relative change in revenue (-0.15 = -15%)",
        affected_line_items="revenue, cogs",
        transmission_fields="demand_sensitivity_index, variable_cost_ratio",
        formula=(
            "revenue_scenario = revenue_base * (1 + magnitude * demand_sensitivity_index); "
            "cogs_scenario = cogs_base * "
            "(1 + magnitude * demand_sensitivity_index * variable_cost_ratio)"
        ),
        rationale=(
            "Revenue falls by the shock scaled by the company's demand "
            "sensitivity. COGS falls by less than revenue, because only the "
            "variable-cost share of COGS shrinks with volume — fixed costs "
            "(e.g. rent, base staffing) don't disappear just because demand did."
        ),
    ),
    "combined_stress": ScenarioAssumption(
        scenario_type="combined_stress",
        default_magnitude=0.0,  # not used directly; combined uses each sub-scenario's own default
        magnitude_meaning="applies all four scenarios above using their own default magnitudes",
        affected_line_items="cogs, revenue, interest_expense",
        transmission_fields="all of the above",
        formula=(
            "Each scenario's dollar-impact (scenario_value - base_value) is computed "
            "independently against the SAME base case, then the deltas are summed "
            "onto the base case."
        ),
        rationale=(
            "Kept additive rather than sequential/compounded: applying the shocks "
            "one after another would make the result depend arbitrarily on the "
            "order chosen, and modelling genuine compounded/interacting effects "
            "(e.g. a rate hike changing behaviour that then changes demand) needs "
            "a full simulation model, which is explicitly out of scope for this "
            "project. This simplification is stated wherever a combined-stress "
            "result is shown, not hidden."
        ),
    ),
}

# The four individual (non-combined) scenario types, in a fixed display order.
INDIVIDUAL_SCENARIO_TYPES = [
    "oil_price_shock",
    "currency_depreciation",
    "interest_rate_hike",
    "demand_slowdown",
]

COMBINED_SCENARIO_TYPE = "combined_stress"

ALL_SCENARIO_TYPES = INDIVIDUAL_SCENARIO_TYPES + [COMBINED_SCENARIO_TYPE]


def get_default_magnitude(scenario_type: str) -> float:
    """Return the documented default magnitude for a given scenario type."""
    if scenario_type not in SCENARIO_ASSUMPTIONS:
        raise KeyError(f"Unknown scenario_type: {scenario_type}")
    return SCENARIO_ASSUMPTIONS[scenario_type].default_magnitude


def get_default_magnitudes_for_combined() -> Dict[str, float]:
    """Return the default magnitude for each individual scenario, used by combined_stress."""
    return {
        scenario_type: SCENARIO_ASSUMPTIONS[scenario_type].default_magnitude
        for scenario_type in INDIVIDUAL_SCENARIO_TYPES
    }
