"""
Tests for app/ml/train_model.py and app/services/ml_risk_service.py.

Trains a REAL model (on the real data/ml_risk_training.csv, which is
fast — under a second) into a pytest tmp_path for every test that needs
one, so tests never depend on — or mutate — a developer's real
app/ml/risk_model.joblib. ml_risk_service's module-level MODEL_PATH is
monkeypatched and its cache cleared (via reload_model()) so each test
starts from a known state.
"""

from pathlib import Path

import pytest

from app.exceptions.custom_exceptions import MLModelNotTrainedError
from app.ml import train_model
from app.services import ml_risk_service

HEALTHY_KPIS = {
    "revenue_growth": 0.08,
    "gross_margin": 0.40,
    "operating_margin": 0.20,
    "net_margin": 0.12,
    "current_ratio": 2.0,
    "quick_ratio": 1.6,
    "debt_to_equity": 0.5,
    "interest_coverage": 5.0,
    "operating_cash_flow_margin": 0.15,
}

DISTRESSED_KPIS = {
    "revenue_growth": -0.15,
    "gross_margin": 0.10,
    "operating_margin": -0.05,
    "net_margin": -0.10,
    "current_ratio": 0.6,
    "quick_ratio": 0.3,
    "debt_to_equity": 2.5,
    "interest_coverage": -1.0,
    "operating_cash_flow_margin": -0.08,
}


# ---------------------------------------------------------------------
# Training / selection logic (app/ml/train_model.py)
# ---------------------------------------------------------------------

def test_training_data_loads_with_expected_columns():
    df = train_model.load_training_data(train_model.DEFAULT_DATA_PATH)
    for feature in train_model.FEATURE_NAMES:
        assert feature in df.columns
    assert train_model.TARGET_COLUMN in df.columns
    assert len(df) > 0


def test_composite_health_score_is_not_a_model_feature():
    """
    Leakage guard: composite_health_score is literally what risk_label
    was thresholded from in data/generate_dataset.py — it must never be
    a model input, or the model would trivially learn the threshold
    rule instead of a genuine relationship between ratios and risk.
    """
    assert "composite_health_score" not in train_model.FEATURE_NAMES


def test_train_and_evaluate_produces_metrics_for_both_models():
    df = train_model.load_training_data(train_model.DEFAULT_DATA_PATH)
    results, _artifacts = train_model.train_and_evaluate(df)

    for key in ("logistic_regression", "random_forest"):
        assert key in results
        metrics = results[key]
        assert 0 <= metrics["accuracy"] <= 1
        assert 0 <= metrics["macro_f1"] <= 1
        assert set(metrics["per_class"].keys()) == {"Low", "Medium", "High"}
        assert metrics["confusion_matrix"]["labels"] == ["Low", "Medium", "High"]
        assert len(metrics["confusion_matrix"]["matrix"]) == 3


def test_select_winner_picks_the_higher_macro_f1():
    results = {
        "logistic_regression": {"macro_f1": 0.90},
        "random_forest": {"macro_f1": 0.80},
    }
    assert train_model.select_winner(results) == "logistic_regression"

    results_reversed = {
        "logistic_regression": {"macro_f1": 0.70},
        "random_forest": {"macro_f1": 0.85},
    }
    assert train_model.select_winner(results_reversed) == "random_forest"


def test_full_training_run_selects_logistic_regression_on_the_real_dataset(tmp_path):
    """
    Documents the actual, real finding on this project's dataset (see
    train_model.py's module docstring for why): Logistic Regression
    beats Random Forest here because the synthetic labels are generated
    by a linear rule. If someone regenerates the training data with a
    genuinely nonlinear labelling rule, this test would need updating —
    that's intentional; it's pinned to keep the "which model actually
    won and why" story honest and current.
    """
    output_path = tmp_path / "risk_model.joblib"
    train_model.main(data_path=train_model.DEFAULT_DATA_PATH, output_path=output_path)

    assert output_path.exists()
    summary_path = output_path.with_suffix(".summary.json")
    assert summary_path.exists()

    import joblib
    bundle = joblib.load(output_path)
    assert bundle["model_type"] == "logistic_regression"
    assert bundle["evaluation_results"]["logistic_regression"]["macro_f1"] >= \
        bundle["evaluation_results"]["random_forest"]["macro_f1"]
    assert "SYNTHETIC" in bundle["training_data_disclaimer"]
    assert len(bundle["feature_importance"]) == len(train_model.FEATURE_NAMES)
    assert abs(sum(f["importance_pct"] for f in bundle["feature_importance"]) - 100.0) < 1.0


# ---------------------------------------------------------------------
# Runtime inference (app/services/ml_risk_service.py)
# ---------------------------------------------------------------------

@pytest.fixture()
def trained_model(tmp_path, monkeypatch):
    """Train a real model into a temp path and point ml_risk_service at it."""
    output_path = tmp_path / "risk_model.joblib"
    train_model.main(data_path=train_model.DEFAULT_DATA_PATH, output_path=output_path)
    monkeypatch.setattr(ml_risk_service, "MODEL_PATH", output_path)
    ml_risk_service.reload_model()
    yield output_path
    ml_risk_service.reload_model.__globals__["_model_bundle"] = None  # reset cache after the test


def test_assess_risk_on_a_clearly_healthy_company_returns_low(trained_model):
    result = ml_risk_service.assess_risk(HEALTHY_KPIS)
    assert result["risk_category"] == "Low"
    assert 0 <= result["confidence"] <= 1
    assert result["imputed_features"] == []
    assert set(result["class_probabilities"].keys()) == {"Low", "Medium", "High"}
    assert abs(sum(result["class_probabilities"].values()) - 1.0) < 1e-6


def test_assess_risk_on_a_clearly_distressed_company_returns_high(trained_model):
    result = ml_risk_service.assess_risk(DISTRESSED_KPIS)
    assert result["risk_category"] == "High"


def test_assess_risk_imputes_missing_features_with_training_medians(trained_model):
    kpis_with_gaps = dict(HEALTHY_KPIS)
    kpis_with_gaps["revenue_growth"] = None
    kpis_with_gaps["interest_coverage"] = None

    result = ml_risk_service.assess_risk(kpis_with_gaps)
    assert set(result["imputed_features"]) == {"revenue_growth", "interest_coverage"}
    assert result["risk_category"] in {"Low", "Medium", "High"}


def test_assess_risk_before_training_raises_clear_error(monkeypatch, tmp_path):
    nonexistent_path = tmp_path / "does_not_exist.joblib"
    monkeypatch.setattr(ml_risk_service, "MODEL_PATH", nonexistent_path)
    ml_risk_service.reload_model.__globals__["_model_bundle"] = None

    with pytest.raises(MLModelNotTrainedError):
        ml_risk_service.assess_risk(HEALTHY_KPIS)


def test_get_model_info_never_exposes_the_raw_model_object(trained_model):
    info = ml_risk_service.get_model_info()
    assert "model" not in info
    assert "scaler" not in info
    assert "training_data_disclaimer" in info
    assert "SYNTHETIC" in info["training_data_disclaimer"]


def test_health_score_and_ml_risk_are_directionally_consistent(trained_model):
    """
    Sanity/integration check: a company with a strong Health Score
    should not be classified as High risk, and vice versa. Uses the
    module's own healthy/distressed fixtures rather than
    analytics_engine directly, keeping this test focused on the ML
    service's behavior.
    """
    from app.services.analytics_engine import compute_health_score

    healthy_score, _ = compute_health_score(HEALTHY_KPIS)
    distressed_score, _ = compute_health_score(DISTRESSED_KPIS)
    assert healthy_score > distressed_score

    healthy_risk = ml_risk_service.assess_risk(HEALTHY_KPIS)["risk_category"]
    distressed_risk = ml_risk_service.assess_risk(DISTRESSED_KPIS)["risk_category"]

    risk_order = {"Low": 0, "Medium": 1, "High": 2}
    assert risk_order[healthy_risk] < risk_order[distressed_risk]
