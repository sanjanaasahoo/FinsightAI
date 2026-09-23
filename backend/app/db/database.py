"""
SQLAlchemy database setup.

Defines:
- `engine`      : the SQLAlchemy engine bound to the configured DATABASE_URL
- `SessionLocal`: a session factory used to create per-request DB sessions
- `Base`        : the declarative base class all ORM models will inherit from
- `get_db`      : a FastAPI dependency that yields a request-scoped session
- `init_db`     : creates all tables known to `Base.metadata` (called at
                   application startup)
- `check_db_connection`: a lightweight connectivity check used by the
                   startup sequence and the health endpoint

No ORM models are defined in this file — this is infrastructure-only.
Domain models (User, Statement, LineItem, Analysis, Scenario,
RiskAssessment, Document, DocumentChunk, QaQuery, AiSummary — per the
architecture document's database design) will be added to
`app/db/models.py` in a later phase and will automatically be picked up
by `init_db()` because they will share this same `Base`.

Note: SQLite holds all *relational* data. The RAG feature's vector data
(chunk embeddings) is intentionally NOT stored here — it lives in local
FAISS index files under `FAISS_INDEX_DIR` (see app/core/config.py).
SQLite only stores chunk *text and metadata* alongside a pointer to that
chunk's row position in its FAISS index.
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# `check_same_thread=False` is required for SQLite when the same connection
# pool may be accessed from different threads within a single process,
# which is the standard pattern for FastAPI + SQLite at this scale (see
# architecture document's Architecture section).
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=settings.DEBUG and not settings.LOG_JSON,
    future=True,
)


class Base(DeclarativeBase):
    """Shared declarative base class for all ORM models in the application."""

    pass


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a request-scoped SQLAlchemy session.

    Usage:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Context-manager variant of a DB session for use outside of FastAPI's
    dependency-injection system (e.g. offline ML training scripts, RAG
    ingestion scripts, or startup routines). Commits on success, rolls
    back on error.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Create all database tables known to `Base.metadata`.

    Safe to call on every application startup — `create_all()` only
    creates tables that don't already exist. In Phase 1, no models are
    registered yet, so this simply verifies the database file/engine is
    reachable and writable.
    """
    logger.info("Initializing database schema (create_all) at %s", settings.DATABASE_URL)
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialization complete.")


def check_db_connection() -> bool:
    """
    Perform a trivial `SELECT 1` to confirm the database is reachable.

    Returns True if the connection succeeds, False otherwise.
    """
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connectivity check succeeded.")
        return True
    except Exception:
        logger.exception("Database connectivity check failed.")
        return False
