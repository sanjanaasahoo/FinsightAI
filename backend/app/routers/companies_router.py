"""
Companies router — read-only endpoints over the companies created by
statement uploads.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Company, FinancialStatement
from app.exceptions.custom_exceptions import NotFoundError
from app.schemas.statement_schema import CompanyOut, StatementOut

router = APIRouter(prefix="/api/companies", tags=["Companies"])


@router.get("", response_model=List[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    """List every company currently in the database."""
    return db.query(Company).order_by(Company.name).all()


@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, db: Session = Depends(get_db)):
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return company


@router.get("/{company_id}/statements", response_model=List[StatementOut])
def list_company_statements(company_id: int, db: Session = Depends(get_db)):
    """List a company's financial statements, ordered oldest -> newest."""
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")

    return (
        db.query(FinancialStatement)
        .filter(FinancialStatement.company_id == company_id)
        .order_by(FinancialStatement.period_start)
        .all()
    )
