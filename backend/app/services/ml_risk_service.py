"""
ML Risk Service — runtime inference over the model trained by
app/ml/train_model.py.

Loads the persisted model bundle (app/ml/risk_model.joblib) once and
caches it in memory. Exposes a single entry point, `assess_risk()`, that
takes a KPI dict (the exact output shape of
analytics_engine.compute_kpis()) and returns a risk classification with
confidence and global feature-importance context.

Design notes:
  - A missing/undefined KPI (e.g. `revenue_growth` on a company's first
    uploaded period, or `interest_coverage` when interest_expense is 0)
    is imputed with that feature's TRAINING-DATA MEDIAN, saved in the
    model bundle — documented explicitly in every response via
    `imputed_features`, never silently substituted without a trace.
  - This module raises a clear, catchable error if the model hasn't been
    trained yet (no risk_model.joblib present) rather than crashing the
    whole app — see MLModelNotTrainedError.
  - No retraining happens at request time; training is an explicit,
    offline, scripted step (see app/ml/train_model.py).
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np

from app.exceptions.custom_exceptions import MLModelNotTrainedError

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "risk_model.joblib"

_model_bundle: Optional[Dict] = None


def _load_bundle() -> Dict:
    """Load and cache the trained model bundle. Raises if it doesn't exist yet."""
    global _model_bundle
    if _model_bundle is not None:
        return _model_bundle

    if not MODEL_PATH.exists():
        raise MLModelNotTrainedError(
            "No trained risk model found. Train one first: "
            "`python3 -m app.ml.train_model` (run from the backend/ directory)."
        )

    logger.info("Loading ML risk model bundle from %s", MODEL_PATH)
    _model_bundle = joblib.load(MODEL_PATH)
    logger.info(
        "Loaded %s risk model (trained_at=%s)",
        _model_bundle.get("model_label"),
        _model_bundle.get("trained_at"),
    )
    return _model_bundle


def reload_model() -> Dict:
    """Force a reload from disk (e.g. after retraining). Returns the fresh bundle."""
    global _model_bundle
    _model_bundle = None
    return _load_bundle()


def get_model_info() -> Dict:
    """
    Everything about the currently-loaded model EXCEPT the model/scaler
    objects themselves — safe to return directly from an API endpoint.
    """
    bundle = _load_bundle()
    return {
        "model_type": bundle["model_type"],
        "model_label": bundle["model_label"],
        "feature_names": bundle["feature_names"],
        "label_classes": bundle["label_classes"],
        "feature_importance": bundle["feature_importance"],
        "evaluation_results": bundle["evaluation_results"],
        "selection_metric": bundle["selection_metric"],
        "training_data_disclaimer": bundle["training_data_disclaimer"],
        "trained_at": bundle["trained_at"],
    }


def _build_feature_vector(bundle: Dict, kpis: Dict[str, Optional[float]]) -> "tuple[np.ndarray, List[str]]":
    """
    Build the model's input vector from a KPI dict, in the bundle's fixed
    feature order, imputing any missing/None value with that feature's
    training-data median.

    Returns (feature_vector, imputed_feature_names).
    """
    feature_names = bundle["feature_names"]
    medians = bundle["feature_medians"]

    values = []
    imputed = []
    for name in feature_names:
        value = kpis.get(name)
        if value is None:
            value = medians[name]
            imputed.append(name)
        values.append(float(value))

    return np.array(values, dtype=float).reshape(1, -1), imputed


def assess_risk(kpis: Dict[str, Optional[float]]) -> Dict:
    """
    Classify financial risk from a computed KPI dict.

    Returns:
        {
          "risk_category": "Low" | "Medium" | "High",
          "confidence": float (0-1, the predicted class's probability),
          "class_probabilities": {"Low": .., "Medium": .., "High": ..},
          "model_used": "Logistic Regression" | "Random Forest",
          "top_contributing_features": [...],   # GLOBAL model importance, not per-instance
          "imputed_features": [...],             # which inputs were missing and median-filled
          "training_data_disclaimer": "...",
        }
    """
    bundle = _load_bundle()
    feature_vector, imputed = _build_feature_vector(bundle, kpis)

    model = bundle["model"]
    scaler = bundle["scaler"]

    model_input = scaler.transform(feature_vector) if scaler is not None else feature_vector

    predicted_class = model.predict(model_input)[0]
    probabilities = model.predict_proba(model_input)[0]
    class_probabilities = {
        cls: round(float(prob), 4)
        for cls, prob in zip(model.classes_, probabilities)
    }
    confidence = class_probabilities[predicted_class]

    if imputed:
        logger.info("Risk assessment imputed %d missing feature(s): %s", len(imputed), imputed)

    return {
        "risk_category": predicted_class,
        "confidence": confidence,
        "class_probabilities": class_probabilities,
        "model_used": bundle["model_label"],
        "top_contributing_features": bundle["feature_importance"],
        "imputed_features": imputed,
        "training_data_disclaimer": bundle["training_data_disclaimer"],
    }
