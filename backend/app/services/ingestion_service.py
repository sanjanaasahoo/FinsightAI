"""
Ingestion service.

Takes a validated, cleaned DataFrame (the output of
validation_service.validate_and_clean) and upserts it into SQLite via
SQLAlchemy:

  - one Company row per distinct company_id (created on first sight,
    updated — including exposure fields — on every subsequent upload,
    so a re-upload can correct a company's profile)
  - one FinancialStatement row per (company_id, period_label) (created
    or updated the same way, so re-uploading the same period overwrites
    it rather than duplicating it)

No KPI computation happens here — this module's only job is persistence.
The Financial Analytics Engine runs separately, on demand, against
whatever is currently persisted (see analyses_router.py).
"""

from typing import Dict, List

import pandas as pd
from sqlalchemy.orm import Session

from app.db.models import Company, FinancialStatement

EXPOSURE_FIELDS = [
    "oil_energy_exposure_pct",
    "import_cost_exposure_pct",
    "export_revenue_exposure_pct",
    "fx_debt_exposure_pct",
    "variable_rate_debt_pct",
    "demand_sensitivity_index",
    "variable_cost_ratio",
]

STATEMENT_FIELDS = [
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


def ingest_dataframe(db: Session, df: pd.DataFrame, source_filename: str) -> Dict:
    """
    Upsert every row of `df` as a Company + FinancialStatement pair.

    Returns a summary dict:
        {
          "companies_created": int, "companies_updated": int,
          "statements_created": int, "statements_updated": int,
          "rows_ingested": int,
        }
    """
    companies_created = 0
    companies_updated = 0
    statements_created = 0
    statements_updated = 0

    # Cache companies AND statements we've already touched in this upload,
    # so a multi-period file for the same company only looks each up once
    # — and, critically, so that if the SAME (company_id, period_label)
    # appears twice within a single upload file, the second occurrence is
    # recognized as an update to the first rather than attempting a second
    # INSERT. Without this cache, two new-statement INSERTs for the same
    # (company_id, period_label) in one batch would both go through (since
    # the session has autoflush=False, so the "does this exist yet" query
    # for the second row wouldn't see the first row's still-unflushed
    # insert) and collide on the UniqueConstraint at commit time.
    company_cache: Dict[str, Company] = {}
    statement_cache: Dict[tuple, FinancialStatement] = {}

    for _, row in df.iterrows():
        external_id = str(row["company_id"])

        company = company_cache.get(external_id)
        if company is None:
            company = db.query(Company).filter(Company.external_id == external_id).one_or_none()

        if company is None:
            company = Company(
                external_id=external_id,
                name=row["company_name"],
                sector=row["sector"],
                currency=row["currency"],
                **{field: float(row[field]) for field in EXPOSURE_FIELDS},
            )
            db.add(company)
            db.flush()  # assigns company.id for the FinancialStatement FK below
            companies_created += 1
        else:
            company.name = row["company_name"]
            company.sector = row["sector"]
            company.currency = row["currency"]
            for field in EXPOSURE_FIELDS:
                setattr(company, field, float(row[field]))
            companies_updated += 1

        company_cache[external_id] = company

        statement_key = (company.id, row["period_label"])
        statement = statement_cache.get(statement_key)
        if statement is None:
            statement = (
                db.query(FinancialStatement)
                .filter(
                    FinancialStatement.company_id == company.id,
                    FinancialStatement.period_label == row["period_label"],
                )
                .one_or_none()
            )

        statement_fields = {field: float(row[field]) for field in STATEMENT_FIELDS}

        if statement is None:
            statement = FinancialStatement(
                company_id=company.id,
                period_label=row["period_label"],
                period_start=str(row["period_start"]),
                period_end=str(row["period_end"]),
                source_filename=source_filename,
                **statement_fields,
            )
            db.add(statement)
            db.flush()  # assigns statement.id and makes it visible to later lookups in this batch
            statements_created += 1
        else:
            statement.period_start = str(row["period_start"])
            statement.period_end = str(row["period_end"])
            statement.source_filename = source_filename
            for field, value in statement_fields.items():
                setattr(statement, field, value)
            statements_updated += 1

        statement_cache[statement_key] = statement

    db.commit()

    return {
        "companies_created": companies_created,
        "companies_updated": companies_updated,
        "statements_created": statements_created,
        "statements_updated": statements_updated,
        "rows_ingested": len(df),
    }
