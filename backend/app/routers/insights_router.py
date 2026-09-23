"""
Insights router — the ONLY part of the API that calls Gemini.

Both endpoints here follow the same shape: gather already-computed
results (KPIs, Health Score, optionally a stored scenario run's impact,
and a freshly-computed ML risk classification), hand that structured
JSON to gemini_service, and return what comes back. Gemini never sees
raw, uncomputed financial data — only the outputs of analytics_engine /
impact_engine / ml_risk_service.

If GEMINI_API_KEY isn't configured, gemini_service raises AIServiceError
(HTTP 503), which the global exception handler in app/main.py turns into
a clean JSON error — this router doesn't need its own try/except for
that; the rest of the platform (analytics, scenarios, ML risk) keeps
working regardless of whether this router's calls succeed.
"""

from typing import Dict, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import FinancialStatement, ScenarioRun
from app.exceptions.custom_exceptions import NotFoundError
from app.schemas.insight_schema import (
    InsightAskOut,
    InsightAskRequest,
    InsightSummaryOut,
    InsightSummaryRequest,
)
from app.services import gemini_service, ml_risk_service
from app.services.analytics_engine import compute_health_score, compute_kpis

router = APIRouter(prefix="/api/insights", tags=["Insights"])


def _find_previous_statement(db: Session, statement: FinancialStatement) -> Optional[FinancialStatement]:
    """Same helper logic as analyses_router.py / risk_router.py."""
    return (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.company_id == statement.company_id,
            FinancialStatement.period_start < statement.period_start,
        )
        .order_by(FinancialStatement.period_start.desc())
        .first()
    )


def _gather_context(db: Session, statement_id: int, scenario_run_id: Optional[int]) -> Dict:
    """
    Resolve everything Gemini needs, all already-computed: base-case KPIs
    + Health Score (freshly computed, consistent with analyses_router.py),
    a stored scenario run's impact if requested, and a freshly-computed
    base-case ML risk classification.
    """
    statement = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).one_or_none()
    if statement is None:
        raise NotFoundError(f"Statement {statement_id} not found.")

    previous_statement = _find_previous_statement(db, statement)
    kpis = compute_kpis(
        statement.as_dict(),
        previous_statement=previous_statement.as_dict() if previous_statement else None,
    )
    health_score, health_score_breakdown = compute_health_score(kpis)

    scenario_impact = None
    if scenario_run_id is not None:
        scenario_run = db.query(ScenarioRun).filter(ScenarioRun.id == scenario_run_id).one_or_none()
        if scenario_run is None:
            raise NotFoundError(f"Scenario run {scenario_run_id} not found.")
        if scenario_run.statement_id != statement.id:
            raise NotFoundError(
                f"Scenario run {scenario_run_id} does not belong to statement {statement_id}."
            )
        scenario_impact = {
            "scenario_type": scenario_run.scenario_type,
            "magnitude": scenario_run.magnitude_json,
            "assumptions": scenario_run.assumptions_json,
            **scenario_run.impact_json,
        }

    risk_classification = ml_risk_service.assess_risk(kpis)

    return {
        "kpis": kpis,
        "health_score": health_score,
        "health_score_breakdown": health_score_breakdown,
        "scenario_impact": scenario_impact,
        "risk_classification": risk_classification,
    }


@router.post("/summary", response_model=InsightSummaryOut)
def generate_summary(request: InsightSummaryRequest, db: Session = Depends(get_db)):
    """
    AI executive summary: overall insight, main risk drivers, scenario
    explanation (if a scenario_run_id was provided), and 2-3 practical
    business considerations — all grounded in already-computed numbers.
    """
    context = _gather_context(db, request.statement_id, request.scenario_run_id)

    summary = gemini_service.generate_financial_summary(
        kpis=context["kpis"],
        health_score=context["health_score"],
        health_score_breakdown=context["health_score_breakdown"],
        scenario_impact=context["scenario_impact"],
        risk_classification=context["risk_classification"],
    )

    return InsightSummaryOut(
        **summary,
        risk_category=context["risk_classification"]["risk_category"],
        risk_confidence=context["risk_classification"]["confidence"],
        model_used=context["risk_classification"]["model_used"],
    )


@router.post("/ask", response_model=InsightAskOut)
def ask_question(request: InsightAskRequest, db: Session = Depends(get_db)):
    """Answer a free-form question about a statement's (optionally, a scenario's) computed results."""
    context = _gather_context(db, request.statement_id, request.scenario_run_id)

    answer = gemini_service.answer_question(
        question=request.question,
        kpis=context["kpis"],
        health_score=context["health_score"],
        health_score_breakdown=context["health_score_breakdown"],
        scenario_impact=context["scenario_impact"],
        risk_classification=context["risk_classification"],
    )

    return InsightAskOut(question=request.question, answer=answer)
