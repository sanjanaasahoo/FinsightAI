"""
Shared Pytest fixtures/configuration for the backend test suite.

Ensures tests run against an isolated, disposable SQLite database file and
isolated storage directories rather than the developer's local
`finsight.db` / `storage/`, so running the test suite never mutates real
development data.
"""

import os
import shutil
from pathlib import Path

# Must be set BEFORE any application module (which reads settings at
# import time via get_settings()) is imported, so this sits at the very
# top of conftest.py, which Pytest always loads first.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_finsight.db")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DOCUMENT_STORAGE_DIR", "./test_storage/documents")
os.environ.setdefault("FAISS_INDEX_DIR", "./test_storage/faiss_indexes")
# Forced override (not setdefault): tests must deterministically exercise
# the "AI insights not configured" path by default, regardless of
# whether the developer running the suite happens to have a real
# GEMINI_API_KEY in their local backend/.env file. Any test that needs a
# "configured" Gemini state monkeypatches app.services.gemini_service's
# get_settings directly rather than relying on this environment variable.
os.environ["GEMINI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_artifacts():
    """Remove the test SQLite file and test storage directory after the run."""
    yield
    test_db_path = "./test_finsight.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    test_storage_root = "./test_storage"
    if os.path.exists(test_storage_root):
        shutil.rmtree(test_storage_root)


@pytest.fixture(autouse=True)
def _reset_database_schema():
    """
    Drop and recreate every table before EACH test function.

    Without this, every test in the suite would share the same
    `test_finsight.db` file for the whole session, so an upload in one
    test would still be sitting there when the next test runs (e.g. a
    test asserting "20 companies created" would instead see "20 updated"
    if it ran after another upload test). Importing app.db.models here
    (not just app.db.database) ensures every ORM model — Company,
    FinancialStatement, Analysis, ScenarioRun — is registered on
    Base.metadata before drop_all/create_all runs.
    """
    from app.db import models  # noqa: F401  (registers models on Base.metadata)
    from app.db.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


# ---------------------------------------------------------------------
# Shared API test fixtures — used across test_api_integration.py,
# test_api_risk.py, and test_api_insights.py.
# ---------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def uploaded_client(client):
    """A TestClient with the full demo dataset already uploaded."""
    from app.core.config import get_settings

    settings = get_settings()
    csv_path = DATA_DIR / "company_financials.csv"
    with open(csv_path, "rb") as f:
        response = client.post(
            f"{settings.API_V1_PREFIX}/statements/upload",
            files={"file": ("company_financials.csv", f, "text/csv")},
        )
    assert response.status_code == 200, response.text
    return client, response.json()


@pytest.fixture()
def first_statement_id(uploaded_client):
    """Convenience fixture: (client, statement_id) for the first uploaded statement."""
    from app.core.config import get_settings

    settings = get_settings()
    client, _summary = uploaded_client
    companies = client.get(f"{settings.API_V1_PREFIX}/companies").json()
    company_id = companies[0]["id"]
    statements = client.get(f"{settings.API_V1_PREFIX}/companies/{company_id}/statements").json()
    return client, statements[-1]["id"]  # last period has a previous period, so revenue_growth is non-null
