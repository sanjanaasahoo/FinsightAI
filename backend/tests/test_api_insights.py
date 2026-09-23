"""
API integration tests for app/routers/insights_router.py.

No real Gemini API calls happen in this file. Two distinct behaviors are
tested:
  1. With GEMINI_API_KEY unset (the default test environment — see
     conftest.py's forced override), both endpoints must return a clean
     503 with a clear message — never an unhandled 500, and never a
     silent success with fabricated content.
  2. With app.services.gemini_service's functions monkeypatched to a
     canned response (simulating a "configured and working" Gemini),
     both endpoints must return the expected shape, correctly combining
     the mocked AI text with the real, independently-computed
     risk_category/confidence/model_used fields.
"""

from app.core.config import get_settings
from app.services import gemini_service

settings = get_settings()


# ---------------------------------------------------------------------
# Graceful degradation when GEMINI_API_KEY is not configured
# ---------------------------------------------------------------------

def test_summary_without_api_key_returns_503_not_500(first_statement_id):
    client, statement_id = first_statement_id

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/summary",
        json={"statement_id": statement_id},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "AIServiceError"
    assert "not configured" in body["message"]


def test_ask_without_api_key_returns_503_not_500(first_statement_id):
    client, statement_id = first_statement_id

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/ask",
        json={"statement_id": statement_id, "question": "How healthy is this company?"},
    )

    assert response.status_code == 503
    assert response.json()["error"] == "AIServiceError"


def test_summary_on_unknown_statement_returns_404_before_attempting_gemini(client):
    """A 404 for a bad statement_id must fire before any Gemini call is attempted."""
    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/summary",
        json={"statement_id": 999999},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------
# Success path (Gemini mocked — never actually called)
# ---------------------------------------------------------------------

def test_summary_with_mocked_gemini_returns_expected_shape(first_statement_id, monkeypatch):
    client, statement_id = first_statement_id

    fake_summary = {
        "overall_insight": "This company shows moderate financial health.",
        "risk_drivers": ["Elevated leverage", "Thin cash flow margin"],
        "scenario_explanation": None,
        "recommendations": ["Reduce short-term debt", "Improve receivables collection"],
    }
    monkeypatch.setattr(gemini_service, "generate_financial_summary", lambda **kwargs: fake_summary)

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/summary",
        json={"statement_id": statement_id},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["overall_insight"] == fake_summary["overall_insight"]
    assert body["risk_drivers"] == fake_summary["risk_drivers"]
    assert body["recommendations"] == fake_summary["recommendations"]
    # These three come from the REAL (unmocked) ML risk service, not from
    # the mocked Gemini call — confirms the router combines both sources.
    assert body["risk_category"] in {"Low", "Medium", "High"}
    assert 0 <= body["risk_confidence"] <= 1
    assert body["model_used"] in {"Logistic Regression", "Random Forest"}


def test_summary_with_scenario_passes_scenario_impact_to_gemini(first_statement_id, monkeypatch):
    client, statement_id = first_statement_id

    scenario_response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "oil_price_shock"},
    )
    scenario_run_id = scenario_response.json()["id"]

    captured = {}

    def fake_summary(**kwargs):
        captured["scenario_impact"] = kwargs.get("scenario_impact")
        return {
            "overall_insight": "x", "risk_drivers": [], "scenario_explanation": "y", "recommendations": [],
        }

    monkeypatch.setattr(gemini_service, "generate_financial_summary", fake_summary)

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/summary",
        json={"statement_id": statement_id, "scenario_run_id": scenario_run_id},
    )

    assert response.status_code == 200, response.text
    assert captured["scenario_impact"] is not None
    assert captured["scenario_impact"]["scenario_type"] == "oil_price_shock"
    assert "health_score_change" in captured["scenario_impact"]


def test_ask_with_mocked_gemini_returns_the_answer(first_statement_id, monkeypatch):
    client, statement_id = first_statement_id

    monkeypatch.setattr(gemini_service, "answer_question", lambda **kwargs: "The net margin is healthy.")

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/ask",
        json={"statement_id": statement_id, "question": "How is the net margin?"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["question"] == "How is the net margin?"
    assert body["answer"] == "The net margin is healthy."


def test_ask_rejects_empty_question(first_statement_id):
    client, statement_id = first_statement_id

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/ask",
        json={"statement_id": statement_id, "question": ""},
    )
    assert response.status_code == 422  # Pydantic min_length=1 validation


def test_summary_with_unknown_scenario_run_returns_404(first_statement_id, monkeypatch):
    client, statement_id = first_statement_id
    monkeypatch.setattr(gemini_service, "generate_financial_summary", lambda **kwargs: {
        "overall_insight": "x", "risk_drivers": [], "recommendations": [],
    })

    response = client.post(
        f"{settings.API_V1_PREFIX}/insights/summary",
        json={"statement_id": statement_id, "scenario_run_id": 999999},
    )
    assert response.status_code == 404
