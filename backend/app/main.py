"""
FinSight AI — FastAPI application entrypoint.

Scope of this phase: application bootstrapping only.
  - Loads configuration
  - Configures logging
  - Ensures local storage directories exist (document uploads + FAISS
    indexes — needed by the RAG feature added in a later phase)
  - Establishes and verifies the SQLite/SQLAlchemy database connection
  - Initializes the database schema (create_all)
  - Registers CORS middleware
  - Registers a global exception handler
  - Exposes a single `/api/health` endpoint confirming the service,
    database, and storage directories are all in place

Statements, Companies, Analyses, Scenarios, Risk (ML), and Insights
(Gemini) routers are all wired in below — financial upload,
KPI/Health-Score analytics, trend analysis, scenario/business-impact
engine, the two-model ML risk classifier, and Gemini-powered
explanations. The RAG/document pipeline is NOT part of this phase and is
not wired in yet.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.database import check_db_connection, init_db
from app.db import models  # noqa: F401  (import registers ORM models on Base.metadata for init_db)
from app.exceptions.custom_exceptions import ApplicationStartupError, FinSightBaseException
from app.routers import (
    analyses_router,
    companies_router,
    insights_router,
    risk_router,
    scenarios_router,
    statements_router,
)

settings = get_settings()

# Logging must be configured before anything else logs a message.
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan handler.

    Runs once on startup (before the app begins accepting requests) and
    once on shutdown.
    """
    logger.info(
        "Starting %s v%s in '%s' environment...",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )

    # 1. Ensure local storage directories exist (document uploads, FAISS
    #    indexes). Created now even though nothing writes to them yet, so
    #    the storage layout is stable and verifiable from this phase on.
    settings.ensure_storage_directories()
    logger.info(
        "Storage directories ready: documents='%s', faiss_indexes='%s'",
        settings.DOCUMENT_STORAGE_DIR,
        settings.FAISS_INDEX_DIR,
    )

    # 2. Verify the database is reachable before proceeding.
    if not check_db_connection():
        raise ApplicationStartupError(
            "Could not establish a connection to the database. "
            f"Check DATABASE_URL='{settings.DATABASE_URL}'."
        )

    # 3. Ensure schema exists (no-op if tables already created).
    init_db()

    logger.info("Startup complete. %s is ready to accept requests.", settings.APP_NAME)

    yield  # ---- application runs here ----

    logger.info("Shutting down %s...", settings.APP_NAME)


def create_app() -> FastAPI:
    """
    Application factory.

    Building the app via a factory function (rather than a bare
    module-level `app = FastAPI()`) keeps the module importable/testable
    without side effects.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "FinSight AI — Financial Health & Business Impact Analytics. "
            "Deterministic financial analytics, scenario simulation, one "
            "classical ML risk classifier, and a small RAG + LLM layer for "
            "grounded Q&A over an optional uploaded annual report."
        ),
        debug=settings.DEBUG,
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Request ID + basic request logging middleware
    # ------------------------------------------------------------------
    @application.middleware("http")
    async def add_request_id_and_log(request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "%s %s -> %s (%.2fms) [request_id=%s]",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        return response

    # ------------------------------------------------------------------
    # Global exception handling
    # ------------------------------------------------------------------
    @application.exception_handler(FinSightBaseException)
    async def finsight_exception_handler(
        request: Request, exc: FinSightBaseException
    ) -> JSONResponse:
        logger.error(
            "Handled application exception on %s %s: %s",
            request.method,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.__class__.__name__,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
            },
        )

    # ------------------------------------------------------------------
    # Domain routers
    # ------------------------------------------------------------------
    application.include_router(statements_router.router)
    application.include_router(companies_router.router)
    application.include_router(analyses_router.router)
    application.include_router(scenarios_router.router)
    application.include_router(risk_router.router)
    application.include_router(insights_router.router)

    # ------------------------------------------------------------------
    # Health check endpoint
    # ------------------------------------------------------------------
    @application.get(f"{settings.API_V1_PREFIX}/health", tags=["System"])
    async def health_check() -> dict:
        """
        Lightweight liveness/readiness endpoint.

        Confirms the API process is running, the database is reachable,
        and the local storage directories used by the RAG feature exist.
        The RAG/document routers are the only thing NOT yet registered
        here — everything else (statements, companies, analyses,
        scenarios, risk, insights) is live.
        """
        db_ok = check_db_connection()
        documents_dir_ok = Path(settings.DOCUMENT_STORAGE_DIR).is_dir()
        faiss_dir_ok = Path(settings.FAISS_INDEX_DIR).is_dir()

        overall_ok = db_ok and documents_dir_ok and faiss_dir_ok

        return {
            "status": "ok" if overall_ok else "degraded",
            "service": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT,
            "database": "connected" if db_ok else "unavailable",
            "storage": {
                "documents_dir": "ready" if documents_dir_ok else "missing",
                "faiss_index_dir": "ready" if faiss_dir_ok else "missing",
            },
        }

    return application


app = create_app()
