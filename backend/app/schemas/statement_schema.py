"""
Pydantic schemas — statements & companies.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class RowError(BaseModel):
    row_index: int
    company_id: Optional[str] = None
    period_label: Optional[str] = None
    errors: List[str]


class UploadSummary(BaseModel):
    filename: str
    companies_created: int
    companies_updated: int
    statements_created: int
    statements_updated: int
    rows_ingested: int
    rows_rejected: int
    row_errors: List[RowError]


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    sector: str
    currency: str
    oil_energy_exposure_pct: float
    import_cost_exposure_pct: float
    export_revenue_exposure_pct: float
    fx_debt_exposure_pct: float
    variable_rate_debt_pct: float
    demand_sensitivity_index: float
    variable_cost_ratio: float


class StatementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    period_label: str
    period_start: str
    period_end: str
    revenue: float
    cogs: float
    operating_expenses: float
    interest_expense: float
    net_income: float
    current_assets: float
    current_liabilities: float
    inventory: float
    total_debt: float
    total_equity: float
    cash_and_equivalents: float
    operating_cash_flow: float
    source_filename: Optional[str] = None
    uploaded_at: datetime
