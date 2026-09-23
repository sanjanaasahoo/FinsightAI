"""
Smoke test: application startup and health endpoint.

Does not test any business/domain logic (there is none yet) — it verifies
that the FastAPI app can be constructed, the lifespan startup sequence
(storage directory creation + DB connectivity + schema init) succeeds,
and the `/api/health` endpoint reports everything as ready.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

settings = get_settings()


def test_health_endpoint_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get(f"{settings.API_V1_PREFIX}/health")

    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"] == "connected"
    assert payload["service"] == settings.APP_NAME
    assert payload["version"] == settings.APP_VERSION
    assert payload["storage"]["documents_dir"] == "ready"
    assert payload["storage"]["faiss_index_dir"] == "ready"


def test_storage_directories_are_created_on_startup() -> None:
    with TestClient(app):
        assert Path(settings.DOCUMENT_STORAGE_DIR).is_dir()
        assert Path(settings.FAISS_INDEX_DIR).is_dir()


def test_unknown_route_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/api/this-route-does-not-exist")

    assert response.status_code == 404
