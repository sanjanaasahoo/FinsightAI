"""
Pydantic schemas — Gemini AI insights.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class InsightSummaryRequest(BaseModel):
    statement_id: int
    scenario_run_id: Optional[int] = Field(
        default=None,
        description="If provided, the summary also explains this scenario's impact.",
    )


class InsightSummaryOut(BaseModel):
    overall_insight: str
    risk_drivers: List[str]
    scenario_explanation: Optional[str] = None
    recommendations: List[str]
    risk_category: str
    risk_confidence: float
    model_used: str


class InsightAskRequest(BaseModel):
    statement_id: int
    scenario_run_id: Optional[int] = None
    question: str = Field(..., min_length=1, max_length=2000)


class InsightAskOut(BaseModel):
    question: str
    answer: str
