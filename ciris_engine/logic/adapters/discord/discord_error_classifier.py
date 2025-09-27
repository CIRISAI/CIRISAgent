"""
Discord error classification and retry logic.

Centralizes all discord.py specific error handling patterns.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Categories of Discord errors."""

    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    PERMISSION = "permission"
    WEBSOCKET = "websocket"
    SERVER = "server"
    SSL_TLS = "ssl_tls"
    UNKNOWN = "unknown"


@dataclass
class ErrorClassification:
    """Result of error classification."""

    category: ErrorCategory
    is_transient: bool
    should_retry: bool
    retry_delay: float
    max_retries: int
    description: str


class DiscordErrorClassifier:
    """
    Classifies Discord errors and determines retry strategies.

    Replaces hardcoded error string matching with structured classification.
    """

    # Network and connection errors - always retry
    NETWORK_ERRORS: Set[str] = {
        "Connection reset by peer",
        "Connection refused",
        "Network is unreachable",
        "Temporary failure in name resolution",
        "Connection timed out",
        "Remote end closed connection",
        "ECONNRESET",
        "EPIPE",
        "ETIMEDOUT",  # Socket timeout errors
        "getaddrinfo failed",  # DNS lookup failures
        "Name or service not known",  # DNS resolution errors
    }

    # WebSocket specific errors - always retry
    WEBSOCKET_ERRORS: Set[str] = {
        "Concurrent call to receive() is not allowed",
        "WebSocket connection is closed.",
        "Shard ID None has stopped responding to the gateway.",
        "Session is closed",
        "Cannot write to closing transport",
    }

    # HTTP server errors - retry with backoff
    SERVER_ERRORS: Set[str] = {
        "HTTP 502",
        "HTTP 503",
        "HTTP 504",
        "CloudFlare",
        "Cloudflare",
    }

    # Rate limiting - retry with longer delay
    RATE_LIMIT_ERRORS: Set[str] = {
        "rate limit",
        "Rate limit",
        "429",
    }

    # SSL/TLS errors - retry with caution
    SSL_TLS_ERRORS: Set[str] = {
        "SSL",
        "TLS",
        "certificate",
    }

    # Authentication errors - don't retry
    AUTH_ERRORS: Set[str] = {
        "401",
        "403",
        "Unauthorized",
        "Forbidden",
        "Invalid token",
    }

    # Permission errors - don't retry
    PERMISSION_ERRORS: Set[str] = {
        "Missing Permissions",
        "Missing Access",
        "Cannot send messages",
    }

    @classmethod
    def classify_error(cls, error: Exception, reconnect_attempts: int = 0) -> ErrorClassification:
        """
        Classify a Discord error and determine retry strategy.

        Args:
            error: The exception that occurred
            reconnect_attempts: Number of previous retry attempts

        Returns:
            ErrorClassification with retry strategy
        """
        error_str = str(error)
        error_type = type(error).__name__

        # First check by exception type (like existing logic)
        if cls._is_connection_exception(error):
            return ErrorClassification(
                category=ErrorCategory.NETWORK,
                is_transient=True,
                should_retry=reconnect_attempts < 10,
                retry_delay=min(5.0 * (2 ** max(0, reconnect_attempts - 1)), 60.0),  # Match existing formula
                max_retries=10,
                description=f"Connection exception ({error_type}): {error_str}",
            )

        # Check for aiohttp exceptions (like existing logic)
        if error.__class__.__module__.startswith("aiohttp"):
            return ErrorClassification(
                category=ErrorCategory.NETWORK,
                is_transient=True,
                should_retry=reconnect_attempts < 8,
                retry_delay=min(2.0**reconnect_attempts, 45.0),
                max_retries=8,
                description=f"Aiohttp error ({error_type}): {error_str}",
            )

        # Discord.py specific exceptions that should NOT retry
        if cls._is_discord_non_retryable(error):
            return ErrorClassification(
                category=ErrorCategory.AUTHENTICATION,
                is_transient=False,
                should_retry=False,
                retry_delay=0.0,
                max_retries=0,
                description=f"Discord auth error ({error_type}): {error_str}",
            )

        # Then check by string patterns
        if cls._matches_any(error_str, cls.NETWORK_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.NETWORK,
                is_transient=True,
                should_retry=reconnect_attempts < 10,
                retry_delay=min(5.0 * (2 ** max(0, reconnect_attempts - 1)), 60.0),  # Match existing formula
                max_retries=10,
                description=f"Network error: {error_str}",
            )

        if cls._matches_any(error_str, cls.WEBSOCKET_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.WEBSOCKET,
                is_transient=True,
                should_retry=reconnect_attempts < 15,
                retry_delay=min(1.5**reconnect_attempts, 30.0),
                max_retries=15,
                description=f"WebSocket error: {error_str}",
            )

        if cls._matches_any(error_str, cls.SERVER_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.SERVER,
                is_transient=True,
                should_retry=reconnect_attempts < 8,
                retry_delay=min(3.0 * (reconnect_attempts + 1), 120.0),  # Start at 3.0, not 3^0
                max_retries=8,
                description=f"Server error: {error_str}",
            )

        if cls._matches_any(error_str, cls.RATE_LIMIT_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.RATE_LIMIT,
                is_transient=True,
                should_retry=reconnect_attempts < 5,
                retry_delay=60.0 + (reconnect_attempts * 30.0),  # Long delays for rate limits
                max_retries=5,
                description=f"Rate limit error: {error_str}",
            )

        if cls._matches_any(error_str, cls.SSL_TLS_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.SSL_TLS,
                is_transient=True,
                should_retry=reconnect_attempts < 3,
                retry_delay=5.0 + (reconnect_attempts * 5.0),
                max_retries=3,
                description=f"SSL/TLS error: {error_str}",
            )

        if cls._matches_any(error_str, cls.AUTH_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.AUTHENTICATION,
                is_transient=False,
                should_retry=False,
                retry_delay=0.0,
                max_retries=0,
                description=f"Authentication error: {error_str}",
            )

        if cls._matches_any(error_str, cls.PERMISSION_ERRORS):
            return ErrorClassification(
                category=ErrorCategory.PERMISSION,
                is_transient=False,
                should_retry=False,
                retry_delay=0.0,
                max_retries=0,
                description=f"Permission error: {error_str}",
            )

        # Unknown error - retry cautiously
        logger.warning(f"Unknown Discord error type: {error_type}, message: {error_str}")
        return ErrorClassification(
            category=ErrorCategory.UNKNOWN,
            is_transient=True,
            should_retry=reconnect_attempts < 3,
            retry_delay=10.0,
            max_retries=3,
            description=f"Unknown error ({error_type}): {error_str}",
        )

    @staticmethod
    def _matches_any(error_str: str, patterns: Set[str]) -> bool:
        """Check if error string matches any pattern in set."""
        return any(pattern.lower() in error_str.lower() for pattern in patterns)

    @staticmethod
    def _is_connection_exception(error: Exception) -> bool:
        """Check if exception is a connection-related type (matches existing logic)."""
        try:
            import discord

            connection_types = (
                RuntimeError,
                discord.ConnectionClosed,
                discord.HTTPException,
                discord.GatewayNotFound,
                ConnectionError,
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                TimeoutError,
                OSError,
            )
            return isinstance(error, connection_types)
        except ImportError:
            # Fallback if discord.py not available
            builtin_types = (
                RuntimeError,
                ConnectionError,
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionRefusedError,
                TimeoutError,
                OSError,
            )
            return isinstance(error, builtin_types)

    @staticmethod
    def _is_discord_non_retryable(error: Exception) -> bool:
        """Check if exception is a Discord non-retryable type (matches existing logic)."""
        try:
            import discord

            non_retryable_types = (
                discord.LoginFailure,
                discord.Forbidden,
            )
            return isinstance(error, non_retryable_types)
        except ImportError:
            return False

    @classmethod
    def log_error_classification(cls, classification: ErrorClassification, attempt: int) -> None:
        """Log error classification with appropriate level."""
        if classification.should_retry:
            logger.warning(
                f"Discord {classification.category.value} error (attempt {attempt}/{classification.max_retries}): "
                f"{classification.description}. Retrying in {classification.retry_delay:.1f}s"
            )
        else:
            logger.error(
                f"Discord {classification.category.value} error (non-recoverable): " f"{classification.description}"
            )
