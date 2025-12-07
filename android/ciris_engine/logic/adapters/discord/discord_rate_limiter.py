"""Discord rate limiting component."""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Dict

from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class RateLimitBucket:
    """Represents a rate limit bucket for Discord API."""

    def __init__(self, limit: int, window: float):
        """Initialize a rate limit bucket.

        Args:
            limit: Maximum requests allowed
            window: Time window in seconds
        """
        self.limit = limit
        self.window = window
        self.remaining = limit
        self.reset_at = time.time() + window
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Acquire permission to make a request.

        Returns:
            Wait time in seconds (0 if can proceed immediately)
        """
        async with self._lock:
            now = time.time()

            # Reset if window expired
            if now >= self.reset_at:
                self.remaining = self.limit
                self.reset_at = now + self.window

            # Check if we can proceed
            if self.remaining > 0:
                self.remaining -= 1
                return 0.0

            # Need to wait
            wait_time = self.reset_at - now
            return wait_time

    def update_from_headers(self, remaining: int, reset_at: float) -> None:
        """Update bucket from Discord rate limit headers.

        Args:
            remaining: Remaining requests from header
            reset_at: Reset timestamp from header
        """
        self.remaining = remaining
        self.reset_at = reset_at


class DiscordRateLimiter:
    """Manages rate limiting for Discord API calls."""

    # Discord's global rate limit
    GLOBAL_LIMIT = 50
    GLOBAL_WINDOW = 1.0  # 1 second

    # Known endpoint limits (per 5 minutes unless specified)
    ENDPOINT_LIMITS = {
        # Messages
        "channels/{channel_id}/messages": {"limit": 5, "window": 5.0},
        "channels/{channel_id}/messages/{message_id}": {"limit": 5, "window": 5.0},
        "channels/{channel_id}/messages/{message_id}/reactions": {"limit": 1, "window": 0.25},
        # Channels
        "channels/{channel_id}": {"limit": 5, "window": 15.0},
        "guilds/{guild_id}/channels": {"limit": 2, "window": 10.0},
        # Users/Members
        "users/{user_id}": {"limit": 5, "window": 15.0},
        "guilds/{guild_id}/members/{user_id}": {"limit": 5, "window": 15.0},
        "guilds/{guild_id}/members/{user_id}/roles/{role_id}": {"limit": 10, "window": 10.0},
        # Webhooks
        "webhooks/{webhook_id}": {"limit": 5, "window": 15.0},
        "webhooks/{webhook_id}/{webhook_token}": {"limit": 30, "window": 60.0},
    }

    def __init__(self, safety_margin: float = 0.1):
        """Initialize rate limiter.

        Args:
            safety_margin: Extra wait time as fraction (0.1 = 10% extra)
        """
        self.safety_margin = safety_margin
        self._global_bucket = RateLimitBucket(self.GLOBAL_LIMIT, self.GLOBAL_WINDOW)
        self._endpoint_buckets: Dict[str, RateLimitBucket] = {}
        self._bucket_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

        # Statistics
        self._stats = {"requests": 0, "rate_limited": 0, "total_wait_time": 0.0, "max_wait_time": 0.0}

    async def acquire(self, endpoint: str, method: str = "GET") -> None:
        """Wait if necessary before making an API call.

        Args:
            endpoint: API endpoint path
            method: HTTP method
        """
        self._stats["requests"] += 1

        # Normalize endpoint for bucket lookup
        bucket_key = self._normalize_endpoint(endpoint)

        # Check global rate limit
        global_wait = await self._global_bucket.acquire()
        if global_wait > 0:
            wait_time = global_wait * (1 + self.safety_margin)
            await self._wait_and_log(wait_time, "global", endpoint)

        # Check endpoint-specific rate limit
        if bucket_key in self.ENDPOINT_LIMITS:
            bucket = await self._get_or_create_bucket(bucket_key)
            endpoint_wait = await bucket.acquire()
            if endpoint_wait > 0:
                wait_time = endpoint_wait * (1 + self.safety_margin)
                await self._wait_and_log(wait_time, bucket_key, endpoint)

    def update_from_response(self, endpoint: str, headers: Dict[str, str]) -> None:
        """Update rate limits from Discord response headers.

        Args:
            endpoint: API endpoint that was called
            headers: Response headers
        """
        # Check for rate limit headers
        remaining_str = headers.get("X-RateLimit-Remaining")
        reset_at_str = headers.get("X-RateLimit-Reset")
        headers.get("X-RateLimit-Bucket")

        if remaining_str is not None and reset_at_str is not None:
            try:
                remaining = int(remaining_str)
                reset_at = float(reset_at_str)

                # Update the appropriate bucket
                bucket_key = self._normalize_endpoint(endpoint)
                if bucket_key in self._endpoint_buckets:
                    self._endpoint_buckets[bucket_key].update_from_headers(remaining, reset_at)

            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to parse rate limit headers: {e}")

    async def handle_rate_limit_response(self, endpoint: str, retry_after: float) -> None:
        """Handle a 429 rate limit response.

        Args:
            endpoint: Endpoint that was rate limited
            retry_after: Seconds to wait before retry
        """
        self._stats["rate_limited"] += 1
        wait_time = retry_after * (1 + self.safety_margin)

        logger.warning(f"Rate limited on {endpoint}, waiting {wait_time:.2f}s")
        await asyncio.sleep(wait_time)

        self._stats["total_wait_time"] += wait_time
        self._stats["max_wait_time"] = max(self._stats["max_wait_time"], wait_time)

    def _normalize_endpoint(self, endpoint: str) -> str:
        """Normalize endpoint path to match bucket patterns.

        Args:
            endpoint: Raw endpoint path

        Returns:
            Normalized endpoint for bucket lookup
        """
        # Remove leading slash
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]

        # Replace IDs with placeholders
        import re

        # Channel endpoints
        endpoint = re.sub(r"channels/\d+", "channels/{channel_id}", endpoint)
        endpoint = re.sub(r"messages/\d+", "messages/{message_id}", endpoint)

        # Guild endpoints
        endpoint = re.sub(r"guilds/\d+", "guilds/{guild_id}", endpoint)
        endpoint = re.sub(r"members/\d+", "members/{user_id}", endpoint)
        endpoint = re.sub(r"roles/\d+", "roles/{role_id}", endpoint)

        # User endpoints
        endpoint = re.sub(r"users/\d+", "users/{user_id}", endpoint)

        # Webhook endpoints
        endpoint = re.sub(r"webhooks/\d+", "webhooks/{webhook_id}", endpoint)
        endpoint = re.sub(r"webhooks/\d+/[\w-]+", "webhooks/{webhook_id}/{webhook_token}", endpoint)

        return endpoint

    async def _get_or_create_bucket(self, bucket_key: str) -> RateLimitBucket:
        """Get or create a rate limit bucket.

        Args:
            bucket_key: Normalized endpoint key

        Returns:
            Rate limit bucket
        """
        async with self._bucket_locks[bucket_key]:
            if bucket_key not in self._endpoint_buckets:
                limits = self.ENDPOINT_LIMITS.get(bucket_key, {"limit": 5, "window": 60.0})
                self._endpoint_buckets[bucket_key] = RateLimitBucket(int(limits["limit"]), limits["window"])
            return self._endpoint_buckets[bucket_key]

    async def _wait_and_log(self, wait_time: float, bucket_type: str, endpoint: str) -> None:
        """Wait and log rate limit delay.

        Args:
            wait_time: Time to wait in seconds
            bucket_type: Type of bucket (global or endpoint)
            endpoint: Endpoint being accessed
        """
        logger.info(f"Rate limit ({bucket_type}) - waiting {wait_time:.2f}s for {endpoint}")
        await asyncio.sleep(wait_time)

        self._stats["total_wait_time"] += wait_time
        self._stats["max_wait_time"] = max(self._stats["max_wait_time"], wait_time)

    def get_stats(self) -> JSONDict:
        """Get rate limiter statistics.

        Returns:
            Statistics dictionary
        """
        return {
            **self._stats,
            "average_wait_time": (
                self._stats["total_wait_time"] / self._stats["requests"] if self._stats["requests"] > 0 else 0.0
            ),
            "buckets_tracked": len(self._endpoint_buckets),
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self._stats = {"requests": 0, "rate_limited": 0, "total_wait_time": 0.0, "max_wait_time": 0.0}
