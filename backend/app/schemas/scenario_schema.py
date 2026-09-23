"""
Pydantic schemas — scenario simulation & business impact.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.services.scenario_assumptions import INDIVIDUAL_SCENARIO_TYPES


class ScenarioSimulateRequest(BaseModel):
    statement_id: int
    scenario_type: str = Field(
        ...,
        description=f"One of: {', '.join(INDIVIDUAL_SCENARIO_TYPES)}",
    )
    magnitude: Optional[float] = Field(
        default=None,
        description="Overrides the scenario's documented default magnitude if provided.",
    )


class StressTestRequest(BaseModel):
    statement_id: int
    magnitudes: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Optional per-scenario magnitude overrides, e.g. "
            '{"oil_price_shock": 0.30}. Any scenario type omitted uses its '
            "documented default."
        ),
    )


class ScenarioRunOut(BaseModel):
    id: int
    statement_id: int
    scenario_type: str
    magnitude_json: Dict[str, Any]
    assumptions_json: Dict[str, Any]
    base_statement_json: Dict[str, Any]
    scenario_statement_json: Dict[str, Any]
    impact_json: Dict[str, Any]
    health_score_base: float
    health_score_scenario: float
    health_score_change: float
    created_at: datetime

    class Config:
        from_attributes = True


class ScenarioTypeInfo(BaseModel):
    scenario_type: str
    default_magnitude: Any
    magnitude_meaning: str
    affected_line_items: str
    transmission_fields: str
    formula: str
    rationale: str
