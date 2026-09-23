"""
Scenarios router — single-scenario simulation, combined stress test, and
retrieval of stored scenario runs.
"""

from dataclasses import asdict
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FinancialStatement, ScenarioRun
from app.exceptions.custom_exceptions import NotFoundError, ScenarioError
from app.schemas.scenario_schema import (
    ScenarioRunOut,
    ScenarioSimulateRequest,
    ScenarioTypeInfo,
    StressTestRequest,
)
from app.services.impact_engine import compute_business_impact
from app.services.scenario_assumptions import (
    ALL_SCENARIO_TYPES,
    COMBINED_SCENARIO_TYPE,
    INDIVIDUAL_SCENARIO_TYPES,
    SCENARIO_ASSUMPTIONS,
    get_default_magnitude,
    get_default_magnitudes_for_combined,
)
from app.services.scenario_engine import apply_combined_stress, apply_scenario

router = APIRouter(prefix="/api/scenarios", tags=["Scenarios"])


@router.get("/types", response_model=List[ScenarioTypeInfo])
def list_scenario_types():
    """
    List every supported scenario type with its documented default
    magnitude, the line items/company-exposure fields it uses, the exact
    formula applied, and the rationale — this is the live, API-servable
    version of data/scenario_assumptions.csv.
    """
    return [ScenarioTypeInfo(**asdict(SCENARIO_ASSUMPTIONS[t])) for t in ALL_SCENARIO_TYPES]


def _get_statement_and_company_or_404(db: Session, statement_id: int) -> FinancialStatement:
    statement = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).one_or_none()
    if statement is None:
        raise NotFoundError(f"Statement {statement_id} not found.")
    return statement


@router.post("/simulate", response_model=ScenarioRunOut)
def simulate_scenario(request: ScenarioSimulateRequest, db: Session = Depends(get_db)):
    """
    Run a single scenario (oil_price_shock / currency_depreciation /
    interest_rate_hike / demand_slowdown) against a statement and persist
    + return the base-vs-scenario Business Impact result.
    """
    if request.scenario_type not in INDIVIDUAL_SCENARIO_TYPES:
        raise ScenarioError(
            f"Unknown scenario_type '{request.scenario_type}'. "
            f"Must be one of: {', '.join(INDIVIDUAL_SCENARIO_TYPES)}. "
            f"(For all four at once, use POST /api/scenarios/stress-test.)"
        )

    statement = _get_statement_and_company_or_404(db, request.statement_id)
    company = statement.company

    magnitude = (
        request.magnitude if request.magnitude is not None
        else get_default_magnitude(request.scenario_type)
    )

    base_dict = statement.as_dict()
    scenario_dict = apply_scenario(base_dict, company.exposure_dict(), request.scenario_type, magnitude)
    impact = compute_business_impact(base_dict, scenario_dict)

    scenario_run = ScenarioRun(
        statement_id=statement.id,
        scenario_type=request.scenario_type,
        magnitude_json={request.scenario_type: magnitude},
        assumptions_json=asdict(SCENARIO_ASSUMPTIONS[request.scenario_type]),
        base_statement_json=base_dict,
        scenario_statement_json=scenario_dict,
        impact_json=impact,
        health_score_base=impact["base"]["health_score"],
        health_score_scenario=impact["scenario"]["health_score"],
        health_score_change=impact["health_score_change"],
    )
    db.add(scenario_run)
    db.commit()
    db.refresh(scenario_run)
    return scenario_run


@router.post("/stress-test", response_model=ScenarioRunOut)
def stress_test(request: StressTestRequest, db: Session = Depends(get_db)):
    """
    Run the combined stress scenario (all four shocks applied additively
    against the same base case — see scenario_assumptions.py's
    `combined_stress` rationale) and persist + return the result.
    """
    statement = _get_statement_and_company_or_404(db, request.statement_id)
    company = statement.company

    effective_magnitudes = get_default_magnitudes_for_combined()
    if request.magnitudes:
        unknown = set(request.magnitudes) - set(INDIVIDUAL_SCENARIO_TYPES)
        if unknown:
            raise ScenarioError(
                f"Unknown scenario_type(s) in magnitudes override: {', '.join(unknown)}. "
                f"Must be a subset of: {', '.join(INDIVIDUAL_SCENARIO_TYPES)}."
            )
        effective_magnitudes.update(request.magnitudes)

    base_dict = statement.as_dict()
    scenario_dict = apply_combined_stress(base_dict, company.exposure_dict(), effective_magnitudes)
    impact = compute_business_impact(base_dict, scenario_dict)

    scenario_run = ScenarioRun(
        statement_id=statement.id,
        scenario_type=COMBINED_SCENARIO_TYPE,
        magnitude_json=effective_magnitudes,
        assumptions_json=asdict(SCENARIO_ASSUMPTIONS[COMBINED_SCENARIO_TYPE]),
        base_statement_json=base_dict,
        scenario_statement_json=scenario_dict,
        impact_json=impact,
        health_score_base=impact["base"]["health_score"],
        health_score_scenario=impact["scenario"]["health_score"],
        health_score_change=impact["health_score_change"],
    )
    db.add(scenario_run)
    db.commit()
    db.refresh(scenario_run)
    return scenario_run


@router.get("/statement/{statement_id}", response_model=List[ScenarioRunOut])
def list_scenario_runs_for_statement(statement_id: int, db: Session = Depends(get_db)):
    _get_statement_and_company_or_404(db, statement_id)
    return (
        db.query(ScenarioRun)
        .filter(ScenarioRun.statement_id == statement_id)
        .order_by(ScenarioRun.created_at.desc())
        .all()
    )


@router.get("/{scenario_run_id}", response_model=ScenarioRunOut)
def get_scenario_run(scenario_run_id: int, db: Session = Depends(get_db)):
    scenario_run = db.query(ScenarioRun).filter(ScenarioRun.id == scenario_run_id).one_or_none()
    if scenario_run is None:
        raise NotFoundError(f"Scenario run {scenario_run_id} not found.")
    return scenario_run
