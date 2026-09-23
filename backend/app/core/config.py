"""
Application configuration module.

Centralizes all environment-driven configuration for the FinSight AI
backend. Values are loaded from environment variables (and, in local
development, from a `.env` file at the backend project root) via
pydantic-settings.

No business logic lives here — this module only defines, validates, and
exposes configuration values via a single cached `get_settings()`
accessor. Settings are grouped into: general app metadata, API/CORS,
database, security/auth, LLM, and RAG (document ingestion + embeddings +
vector store) — the last group is new relative to the platform's original
scope, added to support the optional annual-report Q&A feature.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings with sensible local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # General application metadata
    # ------------------------------------------------------------------
    APP_NAME: str = "FinSight AI"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = Field(
        default="development",
        description="One of: development, staging, production",
    )
    DEBUG: bool = True

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    API_V1_PREFIX: str = "/api"

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    CORS_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Comma-separated list of allowed frontend origins.",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str = Field(
        default="sqlite:///./finsight.db",
        description="SQLAlchemy database URL. SQLite file-based DB.",
    )

    # ------------------------------------------------------------------
    # Security / Auth (used from a later phase onward)
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(
        default="CHANGE_ME_IN_PRODUCTION_SUPER_SECRET_KEY",
        description="Secret key used to sign JWT access tokens.",
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # ------------------------------------------------------------------
    # LLM (used from a later phase onward)
    # ------------------------------------------------------------------
    GEMINI_API_KEY: str = Field(
        default="",
        description="API key for the Gemini model. Loaded from environment; never committed.",
    )
    GEMINI_MODEL_NAME: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model used for explanations, summaries, and RAG answers.",
    )

    # ------------------------------------------------------------------
    # RAG — document ingestion, embeddings, and local vector store
    # (used from a later phase onward; defined now so the configuration
    # surface and storage layout are stable from Phase 1)
    # ------------------------------------------------------------------
    DOCUMENT_STORAGE_DIR: str = Field(
        default="./storage/documents",
        description="Local directory where uploaded PDFs are stored.",
    )
    FAISS_INDEX_DIR: str = Field(
        default="./storage/faiss_indexes",
        description="Local directory where per-document FAISS index files are persisted.",
    )
    EMBEDDING_MODEL_NAME: str = Field(
        default="all-MiniLM-L6-v2",
        description="sentence-transformers model used to embed document chunks and queries.",
    )
    MAX_DOCUMENT_SIZE_MB: int = Field(
        default=20,
        description="Maximum accepted size (MB) for an uploaded financial PDF.",
    )
    RAG_CHUNK_SIZE: int = Field(
        default=800,
        description="Target character length per document chunk.",
    )
    RAG_CHUNK_OVERLAP: int = Field(
        default=150,
        description="Character overlap between consecutive chunks.",
    )
    RAG_TOP_K: int = Field(
        default=5,
        description="Number of chunks retrieved per document Q&A query.",
    )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        allowed = {"development", "staging", "production"}
        normalized = value.lower().strip()
        if normalized not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got '{value}'")
        return normalized

    def ensure_storage_directories(self) -> None:
        """
        Create the local storage directories used by the RAG feature if they
        don't already exist. Safe to call repeatedly (idempotent). Called
        once at application startup.
        """
        Path(self.DOCUMENT_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.FAISS_INDEX_DIR).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton Settings instance."""
    return Settings()
