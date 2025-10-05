from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Union, cast

import httpx

from .auth_store import AuthStore
from .exceptions import CIRISAPIError, CIRISConnectionError, CIRISTimeoutError
from .rate_limiter import AdaptiveRateLimiter

logger = logging.getLogger(__name__)


class Transport:
    """
    HTTP transport layer for CIRIS v1 API (Pre-Beta).

    Handles the SuccessResponse wrapper format automatically.
    All v1 endpoints return data wrapped in a standard format.
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str],
        timeout: float,
        use_auth_store: bool = True,
        rate_limit: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self.use_auth_store = use_auth_store
        self.auth_store = AuthStore() if use_auth_store else None

        # Initialize rate limiter (adaptive by default)
        self.rate_limiter = AdaptiveRateLimiter() if rate_limit else None

        # Try to load stored auth if no API key provided
        if use_auth_store and not api_key and self.auth_store:
            stored_key = self.auth_store.get_api_key(self.base_url)
            if stored_key:
                self.api_key = stored_key
                logger.info(f"Loaded API key from auth store for {self.base_url}")

    def set_api_key(self, api_key: Optional[str], persist: bool = True) -> None:
        """
        Update the API key for authentication.

        Args:
            api_key: The API key to use
            persist: Whether to store the key persistently (default: True)
        """
        self.api_key = api_key

        # Store in auth store if enabled
        if persist and self.use_auth_store and self.auth_store and api_key:
            self.auth_store.store_api_key(api_key, self.base_url)
            logger.info(f"Stored API key in auth store for {self.base_url}")

    async def __aenter__(self) -> "Transport":
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, path: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        if not self._client:
            raise RuntimeError("Transport not started")

        # Apply rate limiting if enabled
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Add API version header
        headers["X-API-Version"] = "v1"

        try:
            resp = await self._client.request(method, url, headers=headers, **kwargs)

            # Record success for adaptive rate limiting
            if self.rate_limiter and hasattr(self.rate_limiter, "record_success"):
                self.rate_limiter.record_success()

        except httpx.TimeoutException as exc:
            raise CIRISTimeoutError(str(exc)) from exc
        except httpx.RequestError as exc:
            raise CIRISConnectionError(str(exc)) from exc

        if resp.status_code >= 400:
            # Handle rate limiting specifically
            if resp.status_code == 429:
                if self.rate_limiter and hasattr(self.rate_limiter, "record_429"):
                    self.rate_limiter.record_429()

            # Try to parse error response
            try:
                error_data = resp.json()
                if "error" in error_data:
                    error = error_data["error"]
                    message = error.get("message", resp.text)
                    raise CIRISAPIError(resp.status_code, message, error.get("code"), error.get("details"))
            except Exception:
                pass
            raise CIRISAPIError(resp.status_code, resp.text)

        # Extract and log response headers
        self._log_response_headers(resp.headers)

        # Handle 204 No Content
        if resp.status_code == 204:
            return None

        # Parse JSON response
        try:
            data = resp.json()

            # v1 API wraps all successful responses in SuccessResponse format
            # Automatically unwrap the data field for convenience
            if isinstance(data, dict) and "data" in data:
                # Log metadata if in debug mode
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Request {data.get('request_id')} took {data.get('duration_ms')}ms")
                return cast(Optional[Dict[str, Any]], data["data"])

            # For backward compatibility or non-standard endpoints
            return cast(Optional[Dict[str, Any]], data)

        except Exception as e:
            raise CIRISAPIError(resp.status_code, f"Failed to parse response: {e}")

    def _log_response_headers(self, headers: Union[Dict[str, Any], httpx.Headers]) -> None:
        """Log important response headers."""
        # Convert headers to dict if needed
        headers_dict = dict(headers) if isinstance(headers, httpx.Headers) else headers

        # Update rate limiter from server headers
        if self.rate_limiter:
            self.rate_limiter.update_from_headers(headers_dict)

        # Rate limiting headers
        if "X-RateLimit-Limit" in headers_dict:
            remaining = headers_dict.get("X-RateLimit-Remaining", "?")
            limit = headers_dict.get("X-RateLimit-Limit", "?")
            reset = headers_dict.get("X-RateLimit-Reset", "?")
            window = headers_dict.get("X-RateLimit-Window", "?")

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Rate limit: {remaining}/{limit} remaining, " f"resets at {reset} ({window} window)")

            # Warn if approaching limit
            try:
                if int(remaining) < int(limit) * 0.1:  # Less than 10% remaining
                    logger.warning(f"Rate limit warning: Only {remaining} requests remaining")
            except (ValueError, TypeError):
                pass

        # API version header
        if "X-API-Version" in headers_dict:
            version = headers_dict["X-API-Version"]
            if not hasattr(self, "_logged_version"):
                logger.info(f"Connected to CIRIS API version: {version}")
                self._logged_version = True

        # Deprecation warnings
        if "X-API-Deprecated" in headers_dict:
            logger.warning(f"API deprecation warning: {headers_dict['X-API-Deprecated']}")
