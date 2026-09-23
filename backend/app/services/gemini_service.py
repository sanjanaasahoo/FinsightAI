"""
Gemini AI Insight Service.

Wraps the Google Gen AI Python SDK (`google-genai` — the current, GA,
unified SDK; see requirements.txt) to turn ALREADY-COMPUTED backend
results into plain-English explanations.

*** THE ONE RULE THIS ENTIRE MODULE EXISTS TO ENFORCE ***
Gemini NEVER calculates, recomputes, or invents a financial number. It
only ever receives a JSON object of results the deterministic backend
(analytics_engine / scenario_engine / impact_engine / ml_risk_service)
has already computed, and is instructed — via a strict system prompt —
to explain those numbers, never to produce new ones. This is enforced at
the prompt level (see `_SYSTEM_INSTRUCTION` below), not via a separate
post-hoc numeric-validation layer — that kind of guardrail is a
reasonable future enhancement, deliberately left out here to keep this
phase's scope simple, as documented in the project README.

*** GRACEFUL DEGRADATION ***
If `GEMINI_API_KEY` is not configured, every function in this module
raises `AIServiceError` (HTTP 503) rather than letting a bare
`google.genai` exception bubble up — the deterministic parts of the
platform (analytics, scenarios, ML risk) must keep working even when
this module can't. The API key itself never appears in source code, in
a response body, or anywhere the frontend could see it — it is read
exclusively from `settings.GEMINI_API_KEY` (environment-variable-backed,
see app/core/config.py).
"""

import json
import logging
from typing import Dict, List, Optional

from app.core.config import get_settings
from app.exceptions.custom_exceptions import AIServiceError

logger = logging.getLogger(__name__)

_client = None  # lazily created, cached google.genai.Client


_SYSTEM_INSTRUCTION = """You are a financial explanation assistant for FinSight AI, a financial \
analytics platform.

You will be given a JSON object containing financial KPIs, a Financial \
Health Score with its component breakdown, and — optionally — a \
scenario/business-impact comparison and an ML-based risk classification. \
Every one of these values was ALREADY COMPUTED by deterministic backend \
code before you ever saw it.

Your ONLY job is to explain these pre-computed results in clear, plain \
English for a business owner, analyst, or consultant who may not have a \
finance background.

Hard rules, no exceptions:
1. You must NEVER calculate, recompute, derive, or invent any financial \
   number, ratio, percentage, or score. Every specific number you \
   mention MUST come directly from the JSON you were given.
2. If the JSON does not contain enough information to answer something, \
   say so explicitly rather than estimating, guessing, or extrapolating.
3. Do not give investment advice, legal advice, or accounting advice — \
   only explain what the computed results show and suggest practical, \
   general business considerations.
4. Keep language plain and concrete. Avoid jargon without a brief \
   explanation."""


_SUMMARY_RESPONSE_INSTRUCTION = """Respond ONLY with a single JSON object matching exactly this shape \
(no markdown fences, no extra commentary outside the JSON):
{
  "overall_insight": "<2-4 sentence plain-English summary of the financial health shown in the data>",
  "risk_drivers": ["<the main factor driving the risk/health picture>", "<another driver, if applicable>"],
  "scenario_explanation": "<plain-English explanation of the scenario impact if scenario data was provided, otherwise null>",
  "recommendations": ["<practical business consideration>", "<another practical consideration>", "<optional third consideration>"]
}"""


def _get_client():
    """
    Lazily create and cache a google.genai.Client. Raises AIServiceError
    (never a bare SDK exception) if GEMINI_API_KEY isn't configured.
    """
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise AIServiceError(
            "GEMINI_API_KEY is not configured. Set it in your .env file to enable "
            "AI insights. All other FinSight AI functionality (analytics, scenarios, "
            "ML risk classification) works without it."
        )

    try:
        from google import genai
    except ImportError as exc:
        raise AIServiceError(
            "The google-genai package is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as exc:
        logger.exception("Failed to initialize the Gemini client.")
        raise AIServiceError(f"Could not initialize the Gemini client: {exc}") from exc

    return _client


def reset_client() -> None:
    """Clear the cached client — used by tests, and useful if the API key changes at runtime."""
    global _client
    _client = None


def _call_gemini(contents: str, *, json_response: bool) -> str:
    """
    Shared low-level call: builds the config, calls generate_content,
    and converts any SDK-level failure into an AIServiceError. Returns
    the raw response text.
    """
    settings = get_settings()
    client = _get_client()  # raises AIServiceError early if GEMINI_API_KEY isn't set — checked
    # before importing the SDK, so a missing key always produces the
    # clear "not configured" message rather than a confusing
    # ModuleNotFoundError on environments where google-genai isn't
    # installed yet either.
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        temperature=0.2,  # low temperature: explanation should be grounded, not creative
        response_mime_type="application/json" if json_response else "text/plain",
    )

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_NAME,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        logger.exception("Gemini API call failed.")
        raise AIServiceError(f"Gemini API call failed: {exc}") from exc

    if not response.text:
        raise AIServiceError("Gemini returned an empty response.")

    return response.text


def _build_context(
    kpis: Dict,
    health_score: float,
    health_score_breakdown: Dict,
    scenario_impact: Optional[Dict] = None,
    risk_classification: Optional[Dict] = None,
) -> Dict:
    """Assemble the structured, already-computed context sent to Gemini."""
    context = {
        "financial_kpis": kpis,
        "financial_health_score": {
            "score": health_score,
            "breakdown": health_score_breakdown,
        },
        "scenario_impact": scenario_impact,  # None if not applicable
        "ml_risk_classification": risk_classification,  # None if not yet assessed
    }
    return context


def generate_financial_summary(
    kpis: Dict,
    health_score: float,
    health_score_breakdown: Dict,
    scenario_impact: Optional[Dict] = None,
    risk_classification: Optional[Dict] = None,
) -> Dict:
    """
    Generate an AI executive summary from already-computed results.

    Returns:
        {
          "overall_insight": str,
          "risk_drivers": [str, ...],
          "scenario_explanation": str | None,
          "recommendations": [str, ...],
        }

    Raises AIServiceError if the key isn't configured, the call fails, or
    Gemini's response isn't valid JSON in the expected shape.
    """
    context = _build_context(kpis, health_score, health_score_breakdown, scenario_impact, risk_classification)

    prompt = (
        f"{_SUMMARY_RESPONSE_INSTRUCTION}\n\n"
        f"Here is the computed data to explain:\n{json.dumps(context, indent=2, default=str)}"
    )

    raw_text = _call_gemini(prompt, json_response=True)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("Gemini summary response was not valid JSON: %s", raw_text[:500])
        raise AIServiceError(
            "Gemini returned a response that could not be parsed as JSON.",
            details={"raw_response_preview": raw_text[:500]},
        ) from exc

    # Defensive defaults — never let a partially-shaped response 500 the request.
    return {
        "overall_insight": parsed.get("overall_insight", ""),
        "risk_drivers": parsed.get("risk_drivers", []) or [],
        "scenario_explanation": parsed.get("scenario_explanation"),
        "recommendations": parsed.get("recommendations", []) or [],
    }


def answer_question(
    question: str,
    kpis: Dict,
    health_score: float,
    health_score_breakdown: Dict,
    scenario_impact: Optional[Dict] = None,
    risk_classification: Optional[Dict] = None,
) -> str:
    """
    Answer a free-form user question about already-computed results.
    Returns plain text (not JSON) since a Q&A answer is naturally
    free-form prose, not a fixed structure.
    """
    context = _build_context(kpis, health_score, health_score_breakdown, scenario_impact, risk_classification)

    prompt = (
        "Answer the user's question using ONLY the information in the JSON context below. "
        "If the answer cannot be determined from this data, say so clearly instead of guessing.\n\n"
        f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
        f"Question: {question}"
    )

    return _call_gemini(prompt, json_response=False).strip()


def is_configured() -> bool:
    """Whether GEMINI_API_KEY is set — lets a router check before attempting a call."""
    return bool(get_settings().GEMINI_API_KEY)
