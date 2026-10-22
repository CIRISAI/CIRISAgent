"""
Simple rate limiting middleware for CIRIS API.

Implements a basic in-memory rate limiter using token bucket algorithm.
"""

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple, cast

import jwt
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


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

    async def is_exhausted(self, client_id: str) -> bool:
        """True when ``client_id`` has no token left. Consumes nothing."""
        async with self._lock:
            if client_id not in self.buckets:
                return False
            tokens, last_update = self.buckets[client_id]
            elapsed = (datetime.now() - last_update).total_seconds()
            return min(self.rate, tokens + elapsed * (self.rate / 60.0)) < 1

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

    def __init__(self, requests_per_minute: int = 60, gateway_secret: Optional[bytes] = None):
        """
        Initialize middleware.

        Args:
            requests_per_minute: Rate limit per minute
            gateway_secret: Secret for verifying JWT tokens (required for user-based rate limiting)
        """
        self.limiter = RateLimiter(requests_per_minute)
        # The user's own messages draw from a bucket of their own, so a UI's
        # background polling can never refuse the message the user just sent.
        self.interact_limiter = RateLimiter(requests_per_minute)
        # Per-IP budget for REJECTED credentials (401s). Buckets are keyed by
        # credential before auth has judged it, so without this a caller could
        # mint a fresh bucket per request by rotating junk tokens. Legitimate
        # callers are never charged against it.
        self.rejected_limiter = RateLimiter(requests_per_minute)
        self.gateway_secret = gateway_secret
        # Exempt paths that should not be rate limited
        self.exempt_paths = {
            "/openapi.json",
            "/docs",
            "/redoc",
            "/emergency/shutdown",  # Emergency endpoints bypass rate limiting
            "/v1/system/health",  # Health checks should not be rate limited
            "/v1/system/adapters",  # Adapter listing for mobile app
            "/v1/setup/adapter-types",  # Adapter type listing for add adapter dialog
        }
        # Static file extensions that should be exempt from rate limiting
        # POSTs that carry the user's own words to the agent.
        self.user_message_paths = {"/v1/agent/interact", "/v1/agent/message"}
        self.exempt_extensions = {
            ".js",
            ".css",
            ".map",
            ".woff",
            ".woff2",
            ".ttf",
            ".otf",
            ".eot",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".svg",
            ".ico",
            ".webp",
            ".mp4",
            ".webm",
            ".txt",
            ".html",  # Static HTML pages from Next.js export
        }

    def _get_gateway_secret(self, request: Request) -> Optional[bytes]:
        """
        Get gateway secret from the authentication service.

        Args:
            request: FastAPI request object with app state

        Returns:
            Gateway secret bytes, or None if not available
        """
        # Try to get from explicitly set gateway_secret first
        if self.gateway_secret:
            return self.gateway_secret

        # Lazy-load from authentication service if available
        if hasattr(request.app.state, "authentication_service"):
            auth_service = request.app.state.authentication_service
            if auth_service and hasattr(auth_service, "gateway_secret"):
                secret = auth_service.gateway_secret
                # Type guard: ensure it's bytes
                if isinstance(secret, bytes):
                    return secret

        return None

    def _extract_user_id_from_jwt(self, token: str, request: Request) -> Optional[str]:
        """
        Extract user ID from JWT token WITH proper signature verification.

        SECURITY: This method verifies the JWT signature before trusting the contents.
        Prevents attackers from forging tokens with arbitrary user IDs to bypass rate limiting.

        Args:
            token: JWT token string
            request: FastAPI request object (for accessing authentication service)

        Returns:
            User ID (wa_id) from verified token's 'sub' claim, or None if verification fails
        """
        gateway_secret = self._get_gateway_secret(request)
        if not gateway_secret:
            # No gateway secret available - cannot verify tokens, fallback to IP-based rate limiting
            logger.debug("No gateway_secret available - cannot verify JWT tokens")
            return None

        try:
            # SECURITY FIX: Verify signature with gateway secret before trusting token contents
            decoded = jwt.decode(token, gateway_secret, algorithms=["HS256"])

            # Extract and validate the 'sub' field
            sub = decoded.get("sub")
            if isinstance(sub, str):
                return sub
            return None
        except jwt.InvalidTokenError as e:
            # Token verification failed - fallback to IP-based rate limiting
            logger.debug(f"JWT verification failed in rate limiter: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            # Unexpected error during verification
            logger.debug(f"Failed to verify JWT in rate limiter: {type(e).__name__}: {e}")
            return None

    def _client_id(self, request: Request, client_host: str) -> str:
        """The bucket this request draws from: one per credential, else one per IP.

        Neither token the agent issues today is an HS256 JWT: a node session is
        ``sess:<wa_id>:<mac>`` and an API key is ``ciris_...``. Keying those by
        IP put every request a desktop UI makes into one bucket of 60/min, and
        behind a reverse proxy it put EVERY USER into one bucket, so one user's
        polling refused another user's message. An unverified credential gets
        its own bucket by digest (never the token itself); forging one buys a
        401 and a charge against the per-IP rejected budget.
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return f"ip_{client_host}"
        token = auth_header[7:]
        if token.startswith("service:"):
            return f"service_{client_host}"
        user_id = self._extract_user_id_from_jwt(token, request)
        if user_id:
            return f"user_{user_id}"
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]
        return f"cred_{digest}"

    @staticmethod
    def _rejected_budget_id(request: Request, client_host: str) -> Optional[str]:
        """Whose budget a rejected credential is charged to, or None for no charge.

        Every request the node reverse-proxies onto this listener arrives from
        127.0.0.1 (BrainAdapter), so the loopback peer address is everyone who
        reaches the brain through the node. Charging it would let one caller
        throttle all of them. From a loopback peer, the forwarded client
        address is used when the proxy supplies one; without it, nothing is
        charged and the node in front is the per-caller throttle. A forwarded
        address is trusted only from loopback, never from a remote peer.
        """
        if client_host in _LOOPBACK_HOSTS:
            forwarded = request.headers.get("X-Forwarded-For", "")
            first = forwarded.split(",")[0].strip() if forwarded else ""
            return f"ip_{first}" if first else None
        return f"ip_{client_host}"

    def _too_many(self, limiter: RateLimiter, client_id: str, request: Request) -> JSONResponse:
        retry_after = limiter.get_retry_after(client_id)
        logger.warning(
            "Rate limit exceeded for %s on %s %s (retry_after=%ds)",
            client_id,
            request.method,
            request.url.path,
            retry_after,
        )
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Too many requests. Please wait {retry_after} seconds before trying again.",
                "error": "rate_limit_exceeded",
                "retry_after": retry_after,
                "message": "You're sending requests too quickly. The system will be ready again shortly.",
            },
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limiter.rate),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Window": "60",
            },
        )

    async def __call__(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request through rate limiter."""
        # Check if path is exempt
        if request.url.path in self.exempt_paths:
            response = await call_next(request)
            return cast(Response, response)

        # Check if request is for a static file (by extension or path prefix)
        path = request.url.path
        if path.startswith("/_next/") or any(path.endswith(ext) for ext in self.exempt_extensions):
            response = await call_next(request)
            return cast(Response, response)

        client_host = request.client.host if request.client else "unknown"
        client_id = self._client_id(request, client_host)
        rejected_id = self._rejected_budget_id(request, client_host)

        if rejected_id and await self.rejected_limiter.is_exhausted(rejected_id):
            return self._too_many(self.rejected_limiter, rejected_id, request)

        limiter = self.limiter
        if request.method == "POST" and path in self.user_message_paths:
            limiter = self.interact_limiter
        if not await limiter.check_rate_limit(client_id):
            return self._too_many(limiter, client_id, request)

        # Process request
        processed_response = await call_next(request)
        typed_response: Response = cast(Response, processed_response)

        if rejected_id and typed_response.status_code == 401:
            await self.rejected_limiter.check_rate_limit(rejected_id)

        # Add rate limit headers to response
        if client_id in limiter.buckets:
            tokens, _ = limiter.buckets[client_id]
            typed_response.headers["X-RateLimit-Limit"] = str(limiter.rate)
            typed_response.headers["X-RateLimit-Remaining"] = str(int(tokens))
            typed_response.headers["X-RateLimit-Window"] = "60"

        return typed_response
