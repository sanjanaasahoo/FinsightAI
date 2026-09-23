"""
API integration tests for app/routers/risk_router.py.

Relies on the trained model artifact committed at app/ml/risk_model.joblib
(produced by `python3 -m app.ml.train_model`) — these tests do NOT retrain
a model, unlike tests/test_ml_risk.py's unit tests, since testing the API
layer's plumbing (request -> stored result -> response shape) is the
point here, not re-proving the ML logic itself.
"""

from app.core.config import get_settings

settings = get_settings()


def test_assess_risk_for_a_statement(first_statement_id):
    client, statement_id = first_statement_id

    response = client.post(
        f"{settings.API_V1_PREFIX}/risk/assess",
        json={"statement_id": statement_id},
    )
    assert response.status_code == 200, response.text
    result = response.json()

    assert result["risk_category"] in {"Low", "Medium", "High"}
    assert 0 <= result["confidence"] <= 1
    assert result["statement_id"] == statement_id
    assert result["scenario_run_id"] is None
    assert len(result["feature_importance_json"]) == 9
    assert set(result["class_probabilities_json"].keys()) == {"Low", "Medium", "High"}


def test_assess_risk_on_unknown_statement_returns_404(client):
    response = client.post(
        f"{settings.API_V1_PREFIX}/risk/assess",
        json={"statement_id": 999999},
    )
    assert response.status_code == 404


def test_assess_risk_for_a_scenario_run(first_statement_id):
    client, statement_id = first_statement_id

    scenario_response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "demand_slowdown"},
    )
    assert scenario_response.status_code == 200
    scenario_run_id = scenario_response.json()["id"]

    risk_response = client.post(
        f"{settings.API_V1_PREFIX}/risk/assess",
        json={"statement_id": statement_id, "scenario_run_id": scenario_run_id},
    )
    assert risk_response.status_code == 200, risk_response.text
    result = risk_response.json()
    assert result["scenario_run_id"] == scenario_run_id


def test_assess_risk_rejects_a_scenario_run_from_a_different_statement(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()

    statements_a = client.get(f"{settings.API_V1_PREFIX}/companies/{companies[0]['id']}/statements").json()
    statements_b = client.get(f"{settings.API_V1_PREFIX}/companies/{companies[1]['id']}/statements").json()

    scenario_response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statements_a[0]["id"], "scenario_type": "oil_price_shock"},
    )
    scenario_run_id = scenario_response.json()["id"]

    mismatched_response = client.post(
        f"{settings.API_V1_PREFIX}/risk/assess",
        json={"statement_id": statements_b[0]["id"], "scenario_run_id": scenario_run_id},
    )
    assert mismatched_response.status_code == 404


def test_get_latest_risk_assessment(first_statement_id):
    client, statement_id = first_statement_id

    not_yet = client.get(f"{settings.API_V1_PREFIX}/risk/statement/{statement_id}/latest")
    assert not_yet.status_code == 404

    client.post(f"{settings.API_V1_PREFIX}/risk/assess", json={"statement_id": statement_id})

    latest = client.get(f"{settings.API_V1_PREFIX}/risk/statement/{statement_id}/latest")
    assert latest.status_code == 200
    assert latest.json()["statement_id"] == statement_id


def test_get_risk_assessment_by_id(first_statement_id):
    client, statement_id = first_statement_id

    created = client.post(f"{settings.API_V1_PREFIX}/risk/assess", json={"statement_id": statement_id})
    assessment_id = created.json()["id"]

    fetched = client.get(f"{settings.API_V1_PREFIX}/risk/{assessment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == assessment_id


def test_get_model_info(client):
    response = client.get(f"{settings.API_V1_PREFIX}/risk/model/info")
    assert response.status_code == 200
    info = response.json()

    assert info["model_type"] in {"logistic_regression", "random_forest"}
    assert set(info["label_classes"]) == {"Low", "Medium", "High"}
    assert "logistic_regression" in info["evaluation_results"]
    assert "random_forest" in info["evaluation_results"]
    assert "SYNTHETIC" in info["training_data_disclaimer"]
    assert len(info["feature_importance"]) == 9
