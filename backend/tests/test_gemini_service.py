"""
Tests for app/services/gemini_service.py.

The google-genai SDK is NEVER actually called in this test file —
`_call_gemini` (the one function that touches the SDK) is monkeypatched
directly in every test, so these tests run offline, deterministically,
and without needing a real GEMINI_API_KEY. `_get_client`'s own behavior
(the GEMINI_API_KEY-missing check) is tested separately by monkeypatching
`get_settings` instead, since that check must fire before any SDK call
is attempted.
"""

import json

import pytest

from app.exceptions.custom_exceptions import AIServiceError
from app.services import gemini_service


class _FakeSettings:
    def __init__(self, api_key: str = "fake-key-123", model_name: str = "gemini-2.5-flash"):
        self.GEMINI_API_KEY = api_key
        self.GEMINI_MODEL_NAME = model_name


@pytest.fixture(autouse=True)
def _reset_gemini_client_cache():
    """Every test starts with a clean cached client and a configured fake key by default."""
    gemini_service.get_settings = lambda: _FakeSettings()
    gemini_service.reset_client()
    yield
    gemini_service.reset_client()


def test_missing_api_key_raises_clear_ai_service_error(monkeypatch):
    monkeypatch.setattr(gemini_service, "get_settings", lambda: _FakeSettings(api_key=""))
    gemini_service.reset_client()

    with pytest.raises(AIServiceError) as exc_info:
        gemini_service.generate_financial_summary(kpis={}, health_score=50, health_score_breakdown={})

    assert "not configured" in exc_info.value.message
    assert exc_info.value.status_code == 503


def test_is_configured_reflects_the_api_key(monkeypatch):
    monkeypatch.setattr(gemini_service, "get_settings", lambda: _FakeSettings(api_key="a-real-looking-key"))
    assert gemini_service.is_configured() is True

    monkeypatch.setattr(gemini_service, "get_settings", lambda: _FakeSettings(api_key=""))
    assert gemini_service.is_configured() is False


def test_generate_financial_summary_parses_valid_json_response(monkeypatch):
    valid_response = json.dumps({
        "overall_insight": "The company looks healthy overall.",
        "risk_drivers": ["Strong liquidity", "Low leverage"],
        "scenario_explanation": None,
        "recommendations": ["Maintain current cash reserves", "Monitor receivables"],
    })
    monkeypatch.setattr(gemini_service, "_call_gemini", lambda contents, json_response: valid_response)

    result = gemini_service.generate_financial_summary(
        kpis={"net_margin": 0.1}, health_score=80, health_score_breakdown={}
    )

    assert result["overall_insight"] == "The company looks healthy overall."
    assert result["risk_drivers"] == ["Strong liquidity", "Low leverage"]
    assert result["scenario_explanation"] is None
    assert len(result["recommendations"]) == 2


def test_generate_financial_summary_fills_defaults_for_missing_keys(monkeypatch):
    """Gemini's response omitting optional keys must never crash the parser."""
    partial_response = json.dumps({"overall_insight": "Some summary."})
    monkeypatch.setattr(gemini_service, "_call_gemini", lambda contents, json_response: partial_response)

    result = gemini_service.generate_financial_summary(kpis={}, health_score=50, health_score_breakdown={})

    assert result["overall_insight"] == "Some summary."
    assert result["risk_drivers"] == []
    assert result["recommendations"] == []
    assert result["scenario_explanation"] is None


def test_generate_financial_summary_raises_on_invalid_json(monkeypatch):
    monkeypatch.setattr(
        gemini_service, "_call_gemini", lambda contents, json_response: "not valid json {{{"
    )

    with pytest.raises(AIServiceError) as exc_info:
        gemini_service.generate_financial_summary(kpis={}, health_score=50, health_score_breakdown={})

    assert "could not be parsed" in exc_info.value.message


def test_answer_question_returns_stripped_plain_text(monkeypatch):
    monkeypatch.setattr(
        gemini_service, "_call_gemini", lambda contents, json_response: "  Here is the answer.  "
    )

    answer = gemini_service.answer_question(
        question="What is the net margin?", kpis={"net_margin": 0.1}, health_score=80, health_score_breakdown={}
    )

    assert answer == "Here is the answer."


def test_answer_question_prompt_includes_the_question_and_context(monkeypatch):
    captured = {}

    def fake_call(contents, json_response):
        captured["contents"] = contents
        captured["json_response"] = json_response
        return "An answer."

    monkeypatch.setattr(gemini_service, "_call_gemini", fake_call)

    gemini_service.answer_question(
        question="Why did the health score drop?",
        kpis={"net_margin": -0.05},
        health_score=30,
        health_score_breakdown={},
    )

    assert "Why did the health score drop?" in captured["contents"]
    assert '"net_margin": -0.05' in captured["contents"]
    assert captured["json_response"] is False  # Q&A responses are plain text, not JSON


def test_generate_financial_summary_requests_json_response(monkeypatch):
    captured = {}

    def fake_call(contents, json_response):
        captured["json_response"] = json_response
        return json.dumps({"overall_insight": "x", "risk_drivers": [], "recommendations": []})

    monkeypatch.setattr(gemini_service, "_call_gemini", fake_call)
    gemini_service.generate_financial_summary(kpis={}, health_score=50, health_score_breakdown={})

    assert captured["json_response"] is True


def test_build_context_only_exposes_the_four_documented_keys():
    context = gemini_service._build_context(
        kpis={"a": 1}, health_score=50, health_score_breakdown={"b": 2},
        scenario_impact=None, risk_classification={"c": 3},
    )
    assert set(context.keys()) == {
        "financial_kpis", "financial_health_score", "scenario_impact", "ml_risk_classification",
    }
    assert context["financial_health_score"] == {"score": 50, "breakdown": {"b": 2}}


def test_context_never_includes_raw_statement_fields():
    """
    Sanity check for the "Gemini never calculates" contract: the context
    built for Gemini is built ONLY from kpis/health_score/scenario_impact/
    risk_classification arguments — there is no code path in
    _build_context that could smuggle in raw, uncomputed statement fields
    (revenue, cogs, etc.) alongside the computed KPIs.
    """
    import inspect
    source = inspect.getsource(gemini_service._build_context)
    assert "statement" not in source.lower()
