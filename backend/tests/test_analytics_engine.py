"""
Tests for app/services/analytics_engine.py.

Uses hand-calculated expected values against a fixed, simple synthetic
statement (not the demo dataset) for the KPI/Health-Score tests, so the
expected numbers are easy to verify by eye in this file — plus a
real-data smoke test using the actual demo dataset.
"""

from pathlib import Path

import pandas as pd
import pytest

from app.services.analytics_engine import compute_health_score, compute_kpis, compute_trend

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# A simple, hand-verifiable statement:
#   revenue 1,000,000 | cogs 600,000 -> gross profit 400,000 -> gross margin 0.40
#   opex 200,000 -> operating income 200,000 -> operating margin 0.20
#   interest 40,000 -> pretax 160,000
#   net_income 120,000 -> net margin 0.12
#   current_assets 500,000 / current_liabilities 250,000 -> current ratio 2.0
#   inventory 100,000 -> quick assets 400,000 -> quick ratio 1.6
#   total_debt 400,000 / total_equity 800,000 -> debt_to_equity 0.5
#   interest_coverage = operating_income / interest_expense = 200,000/40,000 = 5.0
#   operating_cash_flow 150,000 -> ocf margin 0.15
SAMPLE_STATEMENT = {
    "revenue": 1_000_000.0,
    "cogs": 600_000.0,
    "operating_expenses": 200_000.0,
    "interest_expense": 40_000.0,
    "net_income": 120_000.0,
    "current_assets": 500_000.0,
    "current_liabilities": 250_000.0,
    "inventory": 100_000.0,
    "total_debt": 400_000.0,
    "total_equity": 800_000.0,
    "cash_and_equivalents": 150_000.0,
    "operating_cash_flow": 150_000.0,
}


def test_kpi_formulas_match_hand_calculation():
    kpis = compute_kpis(SAMPLE_STATEMENT, previous_statement=None)

    assert kpis["revenue_growth"] is None
    assert kpis["gross_margin"] == pytest.approx(0.40)
    assert kpis["operating_margin"] == pytest.approx(0.20)
    assert kpis["net_margin"] == pytest.approx(0.12)
    assert kpis["current_ratio"] == pytest.approx(2.0)
    assert kpis["quick_ratio"] == pytest.approx(1.6)
    assert kpis["debt_to_equity"] == pytest.approx(0.5)
    assert kpis["interest_coverage"] == pytest.approx(5.0)
    assert kpis["operating_cash_flow_margin"] == pytest.approx(0.15)


def test_revenue_growth_uses_previous_period():
    previous = dict(SAMPLE_STATEMENT)
    previous["revenue"] = 900_000.0

    kpis = compute_kpis(SAMPLE_STATEMENT, previous_statement=previous)
    # (1,000,000 - 900,000) / 900,000
    assert kpis["revenue_growth"] == pytest.approx(100_000 / 900_000)


def test_interest_coverage_is_none_when_interest_expense_is_zero():
    statement = dict(SAMPLE_STATEMENT)
    statement["interest_expense"] = 0.0
    kpis = compute_kpis(statement, previous_statement=None)
    assert kpis["interest_coverage"] is None


def test_health_score_breakdown_sums_to_the_score_and_weights_sum_to_one():
    kpis = compute_kpis(SAMPLE_STATEMENT, previous_statement=None)
    score, breakdown = compute_health_score(kpis)

    manual_sum = sum(c["weighted_contribution"] for c in breakdown["components"].values())
    assert manual_sum == pytest.approx(score, abs=0.03)

    weights_sum = sum(c["weight"] for c in breakdown["components"].values())
    assert weights_sum == pytest.approx(1.0)

    assert 0 <= score <= 100


def test_health_score_is_higher_for_a_strong_statement_than_a_weak_one():
    strong = dict(SAMPLE_STATEMENT)  # gross_margin 0.40, current_ratio 2.0, D/E 0.5 — solid

    weak = dict(SAMPLE_STATEMENT)
    weak["net_income"] = -50_000.0       # losing money
    weak["current_assets"] = 150_000.0   # current ratio drops to 0.6
    weak["total_debt"] = 2_000_000.0     # debt_to_equity jumps to 2.5
    weak["operating_cash_flow"] = -20_000.0

    strong_kpis = compute_kpis(strong, previous_statement=None)
    weak_kpis = compute_kpis(weak, previous_statement=None)

    strong_score, _ = compute_health_score(strong_kpis)
    weak_score, _ = compute_health_score(weak_kpis)

    assert strong_score > weak_score


def test_missing_kpi_normalizes_to_zero_not_excluded():
    """A None KPI value (e.g. undefined ratio) must count as 0, never be skipped."""
    kpis = compute_kpis(SAMPLE_STATEMENT, previous_statement=None)
    kpis["interest_coverage"] = None

    _score, breakdown = compute_health_score(kpis)
    assert breakdown["components"]["leverage"]["metrics"]["interest_coverage"]["normalized_score"] == 0.0


def test_trend_with_insufficient_data_returns_insufficient_data():
    periods = [{
        "period_label": "2024-Q1",
        "statement": SAMPLE_STATEMENT,
        "kpis": compute_kpis(SAMPLE_STATEMENT, previous_statement=None),
    }]
    trend = compute_trend(periods)
    assert trend["revenue"]["direction"] == "insufficient_data"


def test_trend_direction_on_a_clearly_growing_series():
    periods = []
    previous = None
    for i, revenue in enumerate([1_000_000, 1_100_000, 1_210_000, 1_331_000]):
        statement = dict(SAMPLE_STATEMENT)
        statement["revenue"] = float(revenue)
        kpis = compute_kpis(statement, previous_statement=previous)
        periods.append({
            "period_label": f"2024-Q{i+1}",
            "statement": statement,
            "kpis": kpis,
        })
        previous = statement

    trend = compute_trend(periods)
    assert trend["revenue"]["direction"] == "improving"
    assert trend["revenue"]["period_over_period_pct_change"][0] is None
    assert trend["revenue"]["period_over_period_pct_change"][1] == pytest.approx(0.10, abs=1e-6)


def test_kpis_and_health_score_run_cleanly_across_the_full_demo_dataset():
    """
    Real-data smoke test: every one of the 160 demo rows must produce a
    valid, in-range Health Score with no exceptions — this is the same
    computation path the API uses for every uploaded statement.
    """
    df = pd.read_csv(DATA_DIR / "company_financials.csv")

    for company_id, group in df.groupby("company_id"):
        group_sorted = group.sort_values("period_start").to_dict("records")
        previous = None
        for statement in group_sorted:
            kpis = compute_kpis(statement, previous_statement=previous)
            score, breakdown = compute_health_score(kpis)
            assert 0 <= score <= 100
            manual_sum = sum(c["weighted_contribution"] for c in breakdown["components"].values())
            assert manual_sum == pytest.approx(score, abs=0.03)
            previous = statement
