"""
CIRIS SDK Exceptions for v1 API (Pre-Beta).

These exceptions match the error format returned by the v1 API.
"""

from typing import Any, Dict, Optional


class CIRISError(Exception):
    """Base exception for the SDK."""


class CIRISAPIError(CIRISError):
    """
    API errors with status codes and structured error information.

    The v1 API returns errors in a standard format:
    {
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "The requested resource was not found",
            "details": {...}
        }
    }
    """

    def __init__(
        self, status_code: int, message: str, code: Optional[str] = None, details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(f"API Error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details or {}


class CIRISTimeoutError(CIRISError):
    """Request timeout errors."""


class CIRISConnectionError(CIRISError):
    """Connection errors - triggers retry logic."""


class CIRISAuthenticationError(CIRISAPIError):
    """Authentication failed (401)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(401, message, "UNAUTHORIZED")


class CIRISPermissionError(CIRISAPIError):
    """Insufficient permissions (403)."""

    def __init__(self, message: str = "Insufficient permissions", required_role: Optional[str] = None):
        details = {"required_role": required_role} if required_role else {}
        super().__init__(403, message, "FORBIDDEN", details)


class CIRISNotFoundError(CIRISAPIError):
    """Resource not found (404)."""

    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} '{resource_id}' not found"
        super().__init__(404, message, "NOT_FOUND", {"resource_type": resource_type, "resource_id": resource_id})


class CIRISValidationError(CIRISAPIError):
    """Request validation failed (422)."""

    def __init__(self, message: str, validation_errors: Optional[Dict[str, Any]] = None):
        super().__init__(422, message, "VALIDATION_ERROR", validation_errors)
