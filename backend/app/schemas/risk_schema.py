"""
Pydantic schemas — ML risk assessment.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class RiskAssessRequest(BaseModel):
    statement_id: int
    scenario_run_id: Optional[int] = None


class RiskAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    statement_id: int
    scenario_run_id: Optional[int] = None
    risk_category: str
    confidence: float
    class_probabilities_json: Dict[str, float]
    model_used: str
    feature_importance_json: List[Dict[str, Any]]
    imputed_features_json: List[str]
    created_at: datetime


class ModelInfoOut(BaseModel):
    model_type: str
    model_label: str
    feature_names: List[str]
    label_classes: List[str]
    feature_importance: List[Dict[str, Any]]
    evaluation_results: Dict[str, Any]
    selection_metric: str
    training_data_disclaimer: str
    trained_at: str
