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
    """Simple in-memory rate limiter using token bucket algorithm.

    IMPORTANT: This implementation is in-memory only and not suitable for
    multi-instance deployments. For production with multiple API pods,
    consider using Redis or another distributed backend.
    """

    def __init__(self, requests_per_minute: int = 60, max_clients: int = 10000):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Number of requests allowed per minute
            max_clients: Maximum number of client buckets to track (prevents memory exhaustion)
        """
        self.rate = requests_per_minute
        self.max_clients = max_clients
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
            if (now - self._last_cleanup).total_seconds() > self._cleanup_interval:
                self._cleanup_old_entries()
                self._last_cleanup = now

            # Get or create bucket
            if client_id not in self.buckets:
                # Enforce max bucket count to prevent memory exhaustion
                if len(self.buckets) >= self.max_clients:
                    # Remove oldest bucket to make room (LRU-like behavior)
                    oldest_client = min(self.buckets.items(), key=lambda x: x[1][1])[0]
                    del self.buckets[oldest_client]

                # New client starts with full tokens minus the one consumed by this request
                self.buckets[client_id] = (float(self.rate - 1), now)
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

            # No tokens available - update timestamp but don't consume
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
        client_host = request.client.host if request.client else "unknown"
        client_id = None

        # Try to extract user ID from authentication
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix

            # Check for service token format: "service:TOKEN"
            if token.startswith("service:"):
                # Service tokens use IP-based rate limiting
                client_id = f"service_{client_host}"
            else:
                # JWT tokens: use auth prefix with IP
                # TODO: Decode JWT to extract user_id for per-user rate limiting
                # For now, authenticated users share limit per IP
                client_id = f"auth_{client_host}"
        else:
            # No authentication - use IP-based rate limiting
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
        processed_response = await call_next(request)
        typed_response: Response = cast(Response, processed_response)

        # Add rate limit headers to response
        if client_id in self.limiter.buckets:
            tokens, _ = self.limiter.buckets[client_id]
            typed_response.headers["X-RateLimit-Limit"] = str(self.limiter.rate)
            typed_response.headers["X-RateLimit-Remaining"] = str(int(tokens))
            typed_response.headers["X-RateLimit-Window"] = "60"

        return typed_response
