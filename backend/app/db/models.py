"""
ORM model definitions.

SQLite via SQLAlchemy only — no PostgreSQL, no other database. Five
tables, matching exactly what the current build phase needs:

  - Company:             one row per uploaded company (upserted by
                          `company_id` on each upload)
  - FinancialStatement:   one row per company-period financial statement
                          (upserted by (company_id, period_label))
  - Analysis:             cached KPI/Health-Score computation for a
                          statement (recomputed and overwritten in place
                          whenever POST /api/analyses/{statement_id} is
                          called — never silently served stale)
  - ScenarioRun:          a stored scenario/business-impact result for a
                          statement
  - RiskAssessment:       a stored ML risk-classification result for a
                          statement, or for a specific scenario run

No User table and no auth-related columns anywhere — this phase has no
authentication system, per the current scope. If auth is added later, a
`user_id` foreign key can be added to Company without restructuring
anything else.

JSON-typed columns (kpi_json, health_score_breakdown_json, etc.) hold
already-computed, rarely-individually-queried results as JSON text —
consistent with the architecture document's database design rationale
(avoids overnormalizing values that are always read/written as a whole
blob, while keeping columns that ARE queried/joined on — company_id,
period_label, scenario_type — as real relational columns).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(128), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    # Exposure fields — what makes the Scenario Simulation Engine
    # company-specific rather than a flat, company-agnostic adjustment.
    # See data/DATA_DICTIONARY.md for the meaning of each.
    oil_energy_exposure_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    import_cost_exposure_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    export_revenue_exposure_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fx_debt_exposure_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    variable_rate_debt_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    demand_sensitivity_index: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    variable_cost_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    statements: Mapped[list["FinancialStatement"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )

    def exposure_dict(self) -> dict:
        """The subset of fields the Scenario Simulation Engine needs, as a plain dict."""
        return {
            "oil_energy_exposure_pct": self.oil_energy_exposure_pct,
            "import_cost_exposure_pct": self.import_cost_exposure_pct,
            "export_revenue_exposure_pct": self.export_revenue_exposure_pct,
            "fx_debt_exposure_pct": self.fx_debt_exposure_pct,
            "variable_rate_debt_pct": self.variable_rate_debt_pct,
            "demand_sensitivity_index": self.demand_sensitivity_index,
            "variable_cost_ratio": self.variable_cost_ratio,
        }


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("company_id", "period_label", name="uq_company_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)

    period_label: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO date string
    period_end: Mapped[str] = mapped_column(String(10), nullable=False)

    revenue: Mapped[float] = mapped_column(Float, nullable=False)
    cogs: Mapped[float] = mapped_column(Float, nullable=False)
    operating_expenses: Mapped[float] = mapped_column(Float, nullable=False)
    interest_expense: Mapped[float] = mapped_column(Float, nullable=False)
    net_income: Mapped[float] = mapped_column(Float, nullable=False)
    current_assets: Mapped[float] = mapped_column(Float, nullable=False)
    current_liabilities: Mapped[float] = mapped_column(Float, nullable=False)
    inventory: Mapped[float] = mapped_column(Float, nullable=False)
    total_debt: Mapped[float] = mapped_column(Float, nullable=False)
    total_equity: Mapped[float] = mapped_column(Float, nullable=False)
    cash_and_equivalents: Mapped[float] = mapped_column(Float, nullable=False)
    operating_cash_flow: Mapped[float] = mapped_column(Float, nullable=False)

    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="statements")
    analyses: Mapped[list["Analysis"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan"
    )
    scenario_runs: Mapped[list["ScenarioRun"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan"
    )

    def as_dict(self) -> dict:
        """Plain dict of the fields analytics_engine.compute_kpis() expects."""
        return {
            "revenue": self.revenue,
            "cogs": self.cogs,
            "operating_expenses": self.operating_expenses,
            "interest_expense": self.interest_expense,
            "net_income": self.net_income,
            "current_assets": self.current_assets,
            "current_liabilities": self.current_liabilities,
            "inventory": self.inventory,
            "total_debt": self.total_debt,
            "total_equity": self.total_equity,
            "cash_and_equivalents": self.cash_and_equivalents,
            "operating_cash_flow": self.operating_cash_flow,
        }


class Analysis(Base):
    """Cached result of running the Financial Analytics Engine on one statement."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False, unique=True, index=True
    )

    kpi_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    health_score: Mapped[float] = mapped_column(Float, nullable=False)
    health_score_breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    statement: Mapped["FinancialStatement"] = relationship(back_populates="analyses")


class ScenarioRun(Base):
    """A stored scenario simulation + business impact result for one statement."""

    __tablename__ = "scenario_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False, index=True
    )

    scenario_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    magnitude_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    assumptions_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    base_statement_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    scenario_statement_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    impact_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    health_score_base: Mapped[float] = mapped_column(Float, nullable=False)
    health_score_scenario: Mapped[float] = mapped_column(Float, nullable=False)
    health_score_change: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    statement: Mapped["FinancialStatement"] = relationship(back_populates="scenario_runs")


class RiskAssessment(Base):
    """A stored ML risk-classification result for a statement (and, optionally, a scenario run)."""

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    statement_id: Mapped[int] = mapped_column(
        ForeignKey("financial_statements.id"), nullable=False, index=True
    )
    scenario_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("scenario_runs.id"), nullable=True, index=True
    )

    risk_category: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    class_probabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_used: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_importance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    imputed_features_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_kpis_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    statement: Mapped["FinancialStatement"] = relationship()
    scenario_run: Mapped[Optional["ScenarioRun"]] = relationship()
