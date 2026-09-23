"""
Analyses router — runs the Financial Analytics Engine against a stored
statement and returns/persists the result, plus company-level trend
analysis across periods.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Analysis, Company, FinancialStatement
from app.exceptions.custom_exceptions import NotFoundError
from app.schemas.analysis_schema import AnalysisOut, TrendOut
from app.services.analytics_engine import compute_health_score, compute_kpis, compute_trend

router = APIRouter(prefix="/api/analyses", tags=["Analyses"])


def _get_statement_or_404(db: Session, statement_id: int) -> FinancialStatement:
    statement = db.query(FinancialStatement).filter(FinancialStatement.id == statement_id).one_or_none()
    if statement is None:
        raise NotFoundError(f"Statement {statement_id} not found.")
    return statement


def _find_previous_statement(db: Session, statement: FinancialStatement) -> Optional[FinancialStatement]:
    """The same company's chronologically-prior statement, if any."""
    return (
        db.query(FinancialStatement)
        .filter(
            FinancialStatement.company_id == statement.company_id,
            FinancialStatement.period_start < statement.period_start,
        )
        .order_by(FinancialStatement.period_start.desc())
        .first()
    )


@router.post("/{statement_id}", response_model=AnalysisOut)
def run_analysis(statement_id: int, db: Session = Depends(get_db)):
    """
    (Re)compute KPIs + Financial Health Score for a statement and persist
    the result (one row per statement — a re-run overwrites the previous
    result rather than accumulating history, since the point is "what does
    this statement's analysis look like right now").
    """
    statement = _get_statement_or_404(db, statement_id)
    previous_statement = _find_previous_statement(db, statement)

    kpis = compute_kpis(
        statement.as_dict(),
        previous_statement=previous_statement.as_dict() if previous_statement else None,
    )
    health_score, breakdown = compute_health_score(kpis)

    analysis = db.query(Analysis).filter(Analysis.statement_id == statement_id).one_or_none()
    if analysis is None:
        analysis = Analysis(
            statement_id=statement_id,
            kpi_json=kpis,
            health_score=health_score,
            health_score_breakdown_json=breakdown,
        )
        db.add(analysis)
    else:
        analysis.kpi_json = kpis
        analysis.health_score = health_score
        analysis.health_score_breakdown_json = breakdown

    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/{statement_id}", response_model=AnalysisOut)
def get_analysis(statement_id: int, db: Session = Depends(get_db)):
    """
    Retrieve the most recently computed analysis for a statement. Returns
    404 if `run_analysis` (POST) hasn't been called for this statement yet
    — analysis is computed on demand, not automatically on upload, so the
    caller controls when the (cheap, but non-zero) computation happens.
    """
    analysis = db.query(Analysis).filter(Analysis.statement_id == statement_id).one_or_none()
    if analysis is None:
        raise NotFoundError(
            f"No analysis found for statement {statement_id}. "
            f"POST /api/analyses/{statement_id} to compute it first."
        )
    return analysis


@router.get("/company/{company_id}/trend", response_model=TrendOut)
def get_company_trend(company_id: int, db: Session = Depends(get_db)):
    """
    Compute trend analysis across every statement a company has, ordered
    oldest -> newest. Computed on the fly from currently-stored
    statements (does not require `run_analysis` to have been called for
    each individual period first).
    """
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")

    statements: List[FinancialStatement] = (
        db.query(FinancialStatement)
        .filter(FinancialStatement.company_id == company_id)
        .order_by(FinancialStatement.period_start)
        .all()
    )

    if not statements:
        raise NotFoundError(f"Company {company_id} has no statements to analyze.")

    periods = []
    previous_statement = None
    for statement in statements:
        kpis = compute_kpis(
            statement.as_dict(),
            previous_statement=previous_statement.as_dict() if previous_statement else None,
        )
        periods.append({
            "period_label": statement.period_label,
            "statement": statement.as_dict(),
            "kpis": kpis,
        })
        previous_statement = statement

    trend = compute_trend(periods)

    return TrendOut(company_id=company_id, periods_included=len(periods), trend=trend)
