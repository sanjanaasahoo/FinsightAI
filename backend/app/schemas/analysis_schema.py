"""
Pydantic schemas — analytics (KPIs, Financial Health Score, trend).

Response models are intentionally loose (Dict/Optional[float]) for the
KPI and breakdown payloads rather than exhaustively typed field-by-field,
since those shapes are produced directly by analytics_engine.py and
mirroring every key here would just be duplicated, driftable
documentation. The engine module itself is the source of truth for the
exact shape — see its docstrings.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    statement_id: int
    kpi_json: Dict[str, Optional[float]]
    health_score: float
    health_score_breakdown_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrendOut(BaseModel):
    company_id: int
    periods_included: int
    trend: Dict[str, Any]
