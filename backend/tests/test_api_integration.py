"""
API integration tests — the full flow: upload -> statement -> analysis ->
trend -> scenario simulation -> stress test, using the real demo dataset
(data/company_financials.csv) as the upload fixture, against an isolated
test SQLite database.

The `client` and `uploaded_client` fixtures used throughout this file are
defined once, shared, in conftest.py (also used by test_api_risk.py and
test_api_insights.py).
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

settings = get_settings()
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def test_upload_ingests_the_full_demo_dataset(uploaded_client):
    _client, summary = uploaded_client
    assert summary["companies_created"] == 20
    assert summary["statements_created"] == 160
    assert summary["rows_rejected"] == 0
    assert summary["row_errors"] == []


def test_upload_rejects_unsupported_file_type(client):
    response = client.post(
        f"{settings.API_V1_PREFIX}/statements/upload",
        files={"file": ("statement.pdf", b"not a real pdf", "application/pdf")},
    )
    assert response.status_code == 422


def test_re_upload_updates_rather_than_duplicates(uploaded_client):
    client, _first_summary = uploaded_client
    csv_path = DATA_DIR / "company_financials.csv"
    with open(csv_path, "rb") as f:
        response = client.post(
            f"{settings.API_V1_PREFIX}/statements/upload",
            files={"file": ("company_financials.csv", f, "text/csv")},
        )
    summary = response.json()
    assert summary["companies_created"] == 0
    assert summary["companies_updated"] == 20
    assert summary["statements_created"] == 0
    assert summary["statements_updated"] == 160


def test_duplicate_row_within_a_single_upload_does_not_raise(client):
    """
    Regression test: if the SAME (company_id, period_label) appears twice
    within one upload file, the second occurrence must be treated as an
    update to the first, not attempted as a second INSERT (which would
    otherwise collide on the FinancialStatement unique constraint at
    commit time — see ingestion_service.py's statement_cache).
    """
    csv_text = (DATA_DIR / "company_financials.csv").read_text()
    lines = csv_text.splitlines()
    header = lines[0]
    first_data_row = lines[1]
    # Duplicate the first data row (same company_id + period_label) with a
    # slightly different revenue value, appended at the end of the file.
    duplicated_row = first_data_row
    csv_with_duplicate = "\n".join(lines + [duplicated_row])

    response = client.post(
        f"{settings.API_V1_PREFIX}/statements/upload",
        files={"file": ("dup.csv", csv_with_duplicate.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    # 161 rows in the file, but only 160 distinct (company_id, period_label)
    # pairs — the duplicate must be ingested as an update, not a second create.
    assert summary["rows_ingested"] == 161
    assert summary["statements_created"] == 160
    assert summary["statements_updated"] == 1


def test_list_and_get_companies(uploaded_client):
    client, _summary = uploaded_client
    response = client.get(f"{settings.API_V1_PREFIX}/companies")
    assert response.status_code == 200
    companies = response.json()
    assert len(companies) == 20

    first_company_id = companies[0]["id"]
    detail_response = client.get(f"{settings.API_V1_PREFIX}/companies/{first_company_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == first_company_id


def test_get_unknown_company_returns_404(client):
    response = client.get(f"{settings.API_V1_PREFIX}/companies/999999")
    assert response.status_code == 404


def test_list_company_statements(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]

    response = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements")
    assert response.status_code == 200
    statements = response.json()
    assert len(statements) == 8  # 8 quarters per company in the demo dataset


def test_run_and_get_analysis(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[0]["id"]

    # GET before POST -> 404, analysis is computed on demand only.
    get_before = client.get(f"{settings.API_V1_PREFIX}/analyses/{statement_id}")
    assert get_before.status_code == 404

    run_response = client.post(f"{settings.API_V1_PREFIX}/analyses/{statement_id}")
    assert run_response.status_code == 200
    analysis = run_response.json()
    assert 0 <= analysis["health_score"] <= 100
    assert "net_margin" in analysis["kpi_json"]
    assert "components" in analysis["health_score_breakdown_json"]

    get_after = client.get(f"{settings.API_V1_PREFIX}/analyses/{statement_id}")
    assert get_after.status_code == 200
    assert get_after.json()["health_score"] == analysis["health_score"]


def test_company_trend(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]

    response = client.get(f"{settings.API_V1_PREFIX}/analyses/company/{company_id}/trend")
    assert response.status_code == 200
    trend_payload = response.json()
    assert trend_payload["periods_included"] == 8
    assert "revenue" in trend_payload["trend"]
    assert trend_payload["trend"]["revenue"]["direction"] in {
        "improving", "declining", "stable", "insufficient_data",
    }


def test_scenario_types_lists_all_five():
    with TestClient(app) as client:
        response = client.get(f"{settings.API_V1_PREFIX}/scenarios/types")
    assert response.status_code == 200
    types = {t["scenario_type"] for t in response.json()}
    assert types == {
        "oil_price_shock", "currency_depreciation", "interest_rate_hike",
        "demand_slowdown", "combined_stress",
    }


def test_simulate_single_scenario(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "oil_price_shock"},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["scenario_type"] == "oil_price_shock"
    assert "health_score_change" in result
    assert "most_affected_metrics" in result["impact_json"]


def test_simulate_scenario_with_magnitude_override(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "oil_price_shock", "magnitude": 0.50},
    )
    assert response.status_code == 200
    assert response.json()["magnitude_json"]["oil_price_shock"] == 0.50


def test_simulate_scenario_rejects_unknown_type(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "meteor_strike"},
    )
    assert response.status_code == 400


def test_simulate_scenario_rejects_combined_stress_type(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "combined_stress"},
    )
    assert response.status_code == 400


def test_stress_test_combined(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/stress-test",
        json={"statement_id": statement_id},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["scenario_type"] == "combined_stress"
    assert set(result["magnitude_json"].keys()) == {
        "oil_price_shock", "currency_depreciation", "interest_rate_hike", "demand_slowdown",
    }


def test_list_and_get_scenario_runs(uploaded_client):
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    statement_id = statements[-1]["id"]

    client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": statement_id, "scenario_type": "demand_slowdown"},
    )

    list_response = client.get(f"{settings.API_V1_PREFIX}/scenarios/statement/{statement_id}")
    assert list_response.status_code == 200
    runs = list_response.json()
    assert len(runs) == 1

    detail_response = client.get(f"{settings.API_V1_PREFIX}/scenarios/{runs[0]['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == runs[0]["id"]


def test_scenario_simulate_on_unknown_statement_returns_404(client):
    response = client.post(
        f"{settings.API_V1_PREFIX}/scenarios/simulate",
        json={"statement_id": 999999, "scenario_type": "oil_price_shock"},
    )
    assert response.status_code == 404
