"""
Custom exception hierarchy.

Defines the base exception class that all domain-specific exceptions
inherit from: ValidationError, NotFoundError, AnalysisError,
ScenarioError, MLModelNotTrainedError, AIServiceError. Each maps to a
specific HTTP status code and is caught by the global exception handler
registered in app/main.py, so raising one of these anywhere in a
service/router always produces a clean, structured JSON error response
instead of an unhandled 500.
"""

from typing import Any, Dict, Optional


class FinSightBaseException(Exception):
    """
    Base class for all application-specific exceptions.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code to return to the client.
        details: Optional structured details (e.g. field-level validation
                 errors) to include in the JSON error response.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ApplicationStartupError(FinSightBaseException):
    """Raised when a critical startup step (e.g. DB connectivity) fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=500, details=details)


class ValidationError(FinSightBaseException):
    """
    Raised by validation_service.py for a file-level upload problem
    (missing required columns, unparseable file, zero usable rows).
    Maps to HTTP 422 — the request was well-formed but the data was not.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=422, details=details)


class NotFoundError(FinSightBaseException):
    """Raised when a requested company/statement/analysis/scenario id doesn't exist."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=404, details=details)


class AnalysisError(FinSightBaseException):
    """Raised when the Financial Analytics Engine cannot compute a result (e.g. bad inputs)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=400, details=details)


class ScenarioError(FinSightBaseException):
    """Raised for an invalid scenario request (unknown scenario_type, bad magnitude, etc.)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=400, details=details)


class MLModelNotTrainedError(FinSightBaseException):
    """
    Raised when a risk-assessment request arrives but no trained model
    file exists yet. Maps to HTTP 503 — this is a server-side "not ready
    yet" condition, not a problem with the caller's request.
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=503, details=details)


class AIServiceError(FinSightBaseException):
    """
    Raised for any Gemini/AI-insight failure: missing/invalid API key,
    network failure calling the Gemini API, or a malformed response.
    Maps to HTTP 503 — the deterministic parts of the platform must keep
    working even when this is raised; callers should catch this and
    degrade gracefully rather than let it become an unhandled 500 (see
    app/routers/insights_router.py).
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message=message, status_code=503, details=details)
