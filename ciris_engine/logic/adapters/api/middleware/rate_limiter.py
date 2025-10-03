"""
Simple rate limiting middleware for CIRIS API.

Implements a basic in-memory rate limiter using token bucket algorithm.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Tuple, cast

from fastapi import Request, Response
from fastapi.responses import JSONResponse


class RateLimiter:
    """Simple in-memory rate limiter using token bucket algorithm."""

    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Number of requests allowed per minute
        """
        self.rate = requests_per_minute
        self.buckets: Dict[str, Tuple[float, datetime]] = {}
        self._lock = asyncio.Lock()
        self._cleanup_interval = 300  # Cleanup old entries every 5 minutes
        self._last_cleanup = datetime.now()

    async def check_rate_limit(self, client_id: str) -> bool:
        """
        Check if request is within rate limit.

        Args:
            client_id: Unique identifier for client (IP or user)

        Returns:
            True if allowed, False if rate limited
        """
        async with self._lock:
            now = datetime.now()

            # Cleanup old entries periodically
            if (now - self._last_cleanup).seconds > self._cleanup_interval:
                self._cleanup_old_entries()
                self._last_cleanup = now

            # Get or create bucket
            if client_id not in self.buckets:
                self.buckets[client_id] = (float(self.rate), now)
                return True

            tokens, last_update = self.buckets[client_id]

            # Calculate time elapsed and refill tokens
            elapsed = (now - last_update).total_seconds()
            tokens = min(self.rate, tokens + elapsed * (self.rate / 60.0))

            # Check if we have tokens available
            if tokens >= 1:
                tokens -= 1
                self.buckets[client_id] = (tokens, now)
                return True

            # No tokens available
            self.buckets[client_id] = (tokens, now)
            return False

    def _cleanup_old_entries(self) -> None:
        """Remove entries that haven't been used in over an hour."""
        now = datetime.now()
        cutoff = now - timedelta(hours=1)

        to_remove = []
        for client_id, (_, last_update) in self.buckets.items():
            if last_update < cutoff:
                to_remove.append(client_id)

        for client_id in to_remove:
            del self.buckets[client_id]

    def get_retry_after(self, client_id: str) -> int:
        """
        Get seconds until next request is allowed.

        Args:
            client_id: Unique identifier for client

        Returns:
            Seconds to wait before retry
        """
        if client_id not in self.buckets:
            return 0

        tokens, _ = self.buckets[client_id]
        if tokens >= 1:
            return 0

        # Calculate time needed to get 1 token
        tokens_needed = 1 - tokens
        seconds_per_token = 60.0 / self.rate
        return int(tokens_needed * seconds_per_token) + 1


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""

    def __init__(self, requests_per_minute: int = 60):
        """
        Initialize middleware.

        Args:
            requests_per_minute: Rate limit per minute
        """
        self.limiter = RateLimiter(requests_per_minute)
        # Exempt paths that should not be rate limited
        self.exempt_paths = {
            "/openapi.json",
            "/docs",
            "/redoc",
            "/emergency/shutdown",  # Emergency endpoints bypass rate limiting
            "/v1/system/health",  # Health checks should not be rate limited
        }

    async def __call__(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request through rate limiter."""
        # Check if path is exempt
        if request.url.path in self.exempt_paths:
            response = await call_next(request)
            return cast(Response, response)

        # Extract client identifier (prefer authenticated user, fallback to IP)
        client_id = None

        # Try to get user from JWT token if available
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and ":" not in auth_header:
            # This might be a JWT token, but we'll just use a generic "auth" prefix
            # The actual user extraction would require JWT decoding
            client_host = request.client.host if request.client else "unknown"
            client_id = f"auth_{client_host}"
        else:
            # Use IP address
            client_host = request.client.host if request.client else "unknown"
            client_id = f"ip_{client_host}"

        # Check rate limit
        allowed = await self.limiter.check_rate_limit(client_id)

        if not allowed:
            retry_after = self.limiter.get_retry_after(client_id)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "retry_after": retry_after},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limiter.rate),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": "60",
                },
            )

        # Process request
        response = await call_next(request)
        response = cast(Response, response)

        # Add rate limit headers to response
        if client_id in self.limiter.buckets:
            tokens, _ = self.limiter.buckets[client_id]
            response.headers["X-RateLimit-Limit"] = str(self.limiter.rate)
            response.headers["X-RateLimit-Remaining"] = str(int(tokens))
            response.headers["X-RateLimit-Window"] = "60"

        return response
