"""Reddit API error handling with retry logic and classification."""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    LOW = "low"  # Minor issues, automatic recovery
    MEDIUM = "medium"  # Temporary issues, retry possible
    HIGH = "high"  # Serious issues, may need intervention
    CRITICAL = "critical"  # Service-breaking issues


class RedditErrorInfo(BaseModel):
    """Structured information about a Reddit API error."""

    severity: ErrorSeverity
    message: str
    can_retry: bool
    error_type: str
    retry_after: Optional[float] = None
    operation: Optional[str] = None
    endpoint: Optional[str] = None
    suggested_action: Optional[str] = None


class RedditErrorHandler:
    """Error handler for Reddit API operations with exponential backoff."""

    def __init__(self) -> None:
        """Initialize error handler."""
        self._error_counts: dict[str, int] = {}
        self._last_errors: dict[str, datetime] = {}
        self._error_threshold = 5  # Errors before escalation
        self._error_window = timedelta(minutes=5)  # Time window for error counting

    def classify_error(self, error: Exception, operation: str = "unknown") -> RedditErrorInfo:
        """Classify an error and determine retry strategy.

        Args:
            error: The exception that occurred
            operation: What operation was being performed

        Returns:
            Error classification with retry guidance
        """
        error_key = f"{operation}_{type(error).__name__}"
        severity = ErrorSeverity.MEDIUM
        can_retry = True
        retry_after = None
        suggested_action = None

        # Network-level errors (transient, always retryable)
        if isinstance(error, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout)):
            severity = ErrorSeverity.MEDIUM
            can_retry = True
            suggested_action = "exponential_backoff"
            message = f"Network timeout during {operation}: {type(error).__name__}"

        elif isinstance(error, httpx.ConnectError):
            severity = ErrorSeverity.HIGH
            can_retry = True
            suggested_action = "exponential_backoff"
            message = f"Connection error during {operation}: {str(error)}"

        elif isinstance(error, httpx.NetworkError):
            severity = ErrorSeverity.MEDIUM
            can_retry = True
            suggested_action = "exponential_backoff"
            message = f"Network error during {operation}: {str(error)}"

        # HTTP response errors
        elif isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code

            if status_code == 401:
                severity = ErrorSeverity.HIGH
                can_retry = True
                suggested_action = "refresh_token"
                message = "Unauthorized - token may have expired"

            elif status_code == 403:
                severity = ErrorSeverity.HIGH
                can_retry = False
                suggested_action = "check_permissions"
                message = f"Forbidden - no permission for {operation}"

            elif status_code == 404:
                severity = ErrorSeverity.LOW
                can_retry = False
                suggested_action = "verify_resource_exists"
                message = f"Resource not found for {operation}"

            elif status_code == 429:
                severity = ErrorSeverity.LOW
                can_retry = True
                suggested_action = "respect_rate_limit"
                # Extract Retry-After header
                retry_after = self._extract_retry_after(error.response)
                message = f"Rate limited - retry after {retry_after}s"

            elif 500 <= status_code < 600:
                severity = ErrorSeverity.MEDIUM
                can_retry = True
                suggested_action = "exponential_backoff"
                message = f"Reddit server error {status_code} during {operation}"

            else:
                severity = ErrorSeverity.MEDIUM
                message = f"HTTP error {status_code} during {operation}: {error.response.text[:100]}"

        # Runtime errors - check for authentication failures
        elif isinstance(error, RuntimeError):
            error_str = str(error).lower()
            # Authentication failures (suspended account, invalid credentials, OAuth errors)
            # Covers: "authentication failed", "suspended", "invalid credentials"
            # Plus Reddit OAuth error codes: "invalid_grant", "invalid_client"
            # Plus 401 status in token requests (always auth failure, never transient)
            if (
                "authentication failed" in error_str
                or "suspended" in error_str
                or "invalid credentials" in error_str
                or "invalid_grant" in error_str
                or "invalid_client" in error_str
                or ("token request failed" in error_str and "(401)" in error_str)
            ):
                severity = ErrorSeverity.CRITICAL
                can_retry = False  # Don't retry auth failures - requires manual intervention
                suggested_action = "check_account_status"
                message = f"Reddit authentication failure: {str(error)}"
            # Token refresh failures (temporary, non-auth issues like 5xx)
            elif "token request failed" in error_str:
                severity = ErrorSeverity.HIGH
                can_retry = True  # Temporary token issues may resolve
                suggested_action = "exponential_backoff"
                message = f"Token refresh failed: {str(error)}"
            else:
                severity = ErrorSeverity.MEDIUM
                message = f"Runtime error during {operation}: {str(error)}"

        # Generic errors
        else:
            severity = ErrorSeverity.MEDIUM
            message = f"Unexpected error during {operation}: {str(error)}"

        # Track error frequency
        self._track_error(error_key, severity)

        result = RedditErrorInfo(
            severity=severity,
            message=message,
            can_retry=can_retry,
            error_type=type(error).__name__,
            retry_after=retry_after,
            operation=operation,
            suggested_action=suggested_action,
        )

        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical(f"Reddit API critical error: {result.model_dump()}")
        elif severity == ErrorSeverity.HIGH:
            logger.error(f"Reddit API error: {result.model_dump()}")
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning(f"Reddit API warning: {result.model_dump()}")
        else:
            logger.info(f"Reddit API info: {result.model_dump()}")

        return result

    def _extract_retry_after(self, response: httpx.Response) -> float:
        """Extract retry-after value from response headers.

        Args:
            response: HTTP response with potential Retry-After header

        Returns:
            Seconds to wait (defaults to 1.0 if not present)
        """
        retry_after_header = response.headers.get("Retry-After", "1")
        try:
            return float(retry_after_header)
        except ValueError:
            # Header might be HTTP-date format, default to 1 second
            return 1.0

    def _track_error(self, error_key: str, severity: ErrorSeverity) -> None:
        """Track error frequency and escalate if needed.

        Args:
            error_key: Unique key for this error type
            severity: Error severity
        """
        now = datetime.now(timezone.utc)

        # Clean old errors
        cutoff = now - self._error_window
        self._error_counts = {
            k: v for k, v in self._error_counts.items() if k not in self._last_errors or self._last_errors[k] > cutoff
        }

        # Track this error
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        self._last_errors[error_key] = now

        # Check for escalation
        if self._error_counts[error_key] >= self._error_threshold:
            logger.warning(
                f"Error threshold reached for {error_key}: "
                f"{self._error_counts[error_key]} errors in {self._error_window}"
            )

    async def retry_with_backoff(
        self,
        operation: Callable[[], Any],
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        operation_name: str = "reddit_operation",
    ) -> Any:
        """Retry an operation with exponential backoff and jitter.

        Implements industry best practices:
        - Exponential backoff (2^attempt * base_delay)
        - Jitter (random variation to prevent thundering herd)
        - Max retry limit
        - Max delay cap
        - Error classification

        Args:
            operation: Async callable to retry
            max_retries: Maximum number of retry attempts (default: 3)
            base_delay: Base delay in seconds (default: 1.0)
            max_delay: Maximum delay in seconds (default: 60.0)
            operation_name: Name of operation for logging

        Returns:
            Result of the operation

        Raises:
            Last exception if all retries exhausted
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return await operation()

            except Exception as exc:
                last_error = exc
                error_info = self.classify_error(exc, operation_name)

                # Don't retry non-retryable errors
                if not error_info.can_retry:
                    logger.warning(f"{operation_name} failed with non-retryable error: {error_info.message}")
                    raise

                # Last attempt - don't wait
                if attempt == max_retries:
                    logger.error(f"{operation_name} failed after {max_retries + 1} attempts: {error_info.message}")
                    raise

                # Calculate backoff with jitter
                if error_info.retry_after:
                    # Use Retry-After header if available (429 rate limit)
                    delay = error_info.retry_after
                else:
                    # Exponential backoff: 2^attempt * base_delay
                    delay = min((2**attempt) * base_delay, max_delay)
                    # Add jitter: ±25% random variation
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    delay = max(0.1, delay + jitter)

                logger.info(
                    f"{operation_name} attempt {attempt + 1}/{max_retries + 1} failed, "
                    f"retrying in {delay:.2f}s: {error_info.message}"
                )

                await asyncio.sleep(delay)

        # Should not reach here, but just in case
        if last_error:
            raise last_error
        raise RuntimeError(f"{operation_name} failed with unknown error")

    def get_error_stats(self) -> dict[str, Any]:
        """Get current error statistics.

        Returns:
            Error statistics including counts, threshold, and window
        """
        return {
            "error_counts": self._error_counts.copy(),
            "threshold": self._error_threshold,
            "window_minutes": self._error_window.total_seconds() / 60,
        }
