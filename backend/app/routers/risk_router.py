"""
Risk router — runs the trained ML Risk Module against either:
  - a statement's BASE CASE KPIs (default), or
  - a specific scenario run's SCENARIO CASE KPIs (if `scenario_run_id` is
    given), reusing the KPIs already computed and stored by
    scenarios_router.py's simulate/stress-test endpoints — no
    recomputation needed, since impact_engine.py already ran the exact
    same Financial Analytics Engine on the scenario-adjusted statement.

This lets a caller ask "what does risk look like right now" AND "what
would risk look like under this scenario" through the same endpoint
shape, which is also exactly the pair of facts the AI Insight Service
(insights_router.py) synthesizes into an explanation.
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FinancialStatement, RiskAssessment, ScenarioRun
from app.exceptions.custom_exceptions import NotFoundError
from app.schemas.risk_schema import ModelInfoOut, RiskAssessmentOut, RiskAssessRequest
from app.services import ml_risk_service
from app.services.analytics_engine import compute_kpis

router = APIRouter(prefix="/api/risk", tags=["Risk"])


def _find_previous_statement(db: Session, statement: FinancialStatement) -> Optional[FinancialStatement]:
    """Same helper logic as analyses_router.py — kept local rather than imported to
    avoid coupling two routers together over a private helper function."""
    return (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.company_id == statement.company_id,
            FinancialStatement.period_start < statement.period_start,
        )
        .order_by(FinancialStatement.period_start.desc())
        .first()
    )


def _resolve_kpis(db: Session, statement: FinancialStatement, scenario_run: Optional[ScenarioRun]) -> Dict:
    """
    Either the statement's base-case KPIs (freshly computed, consistent
    with analyses_router.py) or a stored scenario run's scenario-case
    KPIs — whichever the caller asked for.
    """
    if scenario_run is not None:
        return scenario_run.impact_json["scenario"]["kpis"]

    previous_statement = _find_previous_statement(db, statement)
    return compute_kpis(
        statement.as_dict(),
        previous_statement=previous_statement.as_dict() if previous_statement else None,
    )


@router.post("/assess", response_model=RiskAssessmentOut)
def assess_risk(request: RiskAssessRequest, db: Session = Depends(get_db)):
    """
    Classify financial risk (Low/Medium/High) for a statement's base
    case, or — if `scenario_run_id` is provided — for that scenario's
    projected case. Persists and returns the result.
    """
    statement = db.query(FinancialStatement).filter(FinancialStatement.id == request.statement_id).one_or_none()
    if statement is None:
        raise NotFoundError(f"Statement {request.statement_id} not found.")

    scenario_run = None
    if request.scenario_run_id is not None:
        scenario_run = db.query(ScenarioRun).filter(ScenarioRun.id == request.scenario_run_id).one_or_none()
        if scenario_run is None:
            raise NotFoundError(f"Scenario run {request.scenario_run_id} not found.")
        if scenario_run.statement_id != statement.id:
            raise NotFoundError(
                f"Scenario run {request.scenario_run_id} does not belong to statement {request.statement_id}."
            )

    kpis = _resolve_kpis(db, statement, scenario_run)
    result = ml_risk_service.assess_risk(kpis)

    risk_assessment = RiskAssessment(
        statement_id=statement.id,
        scenario_run_id=scenario_run.id if scenario_run else None,
        risk_category=result["risk_category"],
        confidence=result["confidence"],
        class_probabilities_json=result["class_probabilities"],
        model_used=result["model_used"],
        feature_importance_json=result["top_contributing_features"],
        imputed_features_json=result["imputed_features"],
        input_kpis_json=kpis,
    )
    db.add(risk_assessment)
    db.commit()
    db.refresh(risk_assessment)
    return risk_assessment


@router.get("/statement/{statement_id}/latest", response_model=RiskAssessmentOut)
def get_latest_risk_assessment(statement_id: int, db: Session = Depends(get_db)):
    """Most recent base-case (no scenario_run_id) risk assessment for a statement."""
    assessment = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.statement_id == statement_id, RiskAssessment.scenario_run_id.is_(None))
        .order_by(RiskAssessment.created_at.desc())
        .first()
    )
    if assessment is None:
        raise NotFoundError(
            f"No risk assessment found for statement {statement_id}. "
            f"POST /api/risk/assess first."
        )
    return assessment


@router.get("/{risk_assessment_id}", response_model=RiskAssessmentOut)
def get_risk_assessment(risk_assessment_id: int, db: Session = Depends(get_db)):
    assessment = db.query(RiskAssessment).filter(RiskAssessment.id == risk_assessment_id).one_or_none()
    if assessment is None:
        raise NotFoundError(f"Risk assessment {risk_assessment_id} not found.")
    return assessment


@router.get("/model/info", response_model=ModelInfoOut)
def get_model_info():
    """
    Everything about the currently-loaded ML model: which of the two
    trained models was selected and why, both models' held-out
    evaluation metrics (accuracy/precision/recall/F1/confusion matrix),
    global feature importance, and the synthetic-training-data
    disclaimer.
    """
    return ml_risk_service.get_model_info()
