"""
Rate limiting for CIRIS SDK.

Provides client-side rate limiting to prevent hitting server limits.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter with automatic refill.

    Implements a token bucket algorithm that:
    - Starts with a full bucket of tokens
    - Consumes tokens for each request
    - Refills tokens at a steady rate
    - Blocks when no tokens available
    """

    def __init__(self, requests_per_minute: int = 60, burst_size: Optional[int] = None):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Sustained request rate (default: 60)
            burst_size: Maximum burst size (default: same as rate)
        """
        self.rate: float = float(requests_per_minute)
        self.burst_size = burst_size or requests_per_minute
        self.tokens = float(self.burst_size)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

        # Calculate refill rate (tokens per second)
        self.refill_rate = self.rate / 60.0

        logger.info(f"Rate limiter initialized: {self.rate} req/min, " f"burst size: {self.burst_size}")

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens, blocking if necessary.

        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update

                # Refill tokens based on elapsed time
                self.tokens = min(self.burst_size, self.tokens + elapsed * self.refill_rate)
                self.last_update = now

                # Check if we have enough tokens
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                # Calculate wait time
                tokens_needed = tokens - self.tokens
                wait_time = tokens_needed / self.refill_rate

                logger.debug(f"Rate limit: need {tokens_needed:.1f} tokens, " f"waiting {wait_time:.1f}s")

                # Wait for tokens to refill
                await asyncio.sleep(wait_time)

    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """
        Update rate limits from response headers.

        Args:
            headers: Response headers containing rate limit info
        """
        # Parse rate limit headers
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        window = headers.get("X-RateLimit-Window")

        if not all([limit, remaining]):
            return

        # Type narrowing - we know limit and remaining are not None
        assert limit is not None
        assert remaining is not None

        try:
            limit_val = int(limit)
            remaining_val = int(remaining)

            # Update our rate if server's is different
            if window:
                window_minutes = int(window) / 60
                server_rate = limit_val / window_minutes
                if abs(server_rate - self.rate) > 1:
                    logger.info(f"Updating rate limit from server: " f"{self.rate} -> {server_rate} req/min")
                    self.rate = server_rate
                    self.refill_rate = self.rate / 60.0

            # Sync tokens with server's count
            # Be conservative - use minimum of our count and server's
            self.tokens = min(self.tokens, float(remaining_val))

            # Log if we're getting close to limit
            if remaining_val < limit_val * 0.2:  # Less than 20% remaining
                logger.warning(f"Rate limit warning: {remaining_val}/{limit_val} remaining")

        except (ValueError, TypeError) as e:
            logger.debug(f"Failed to parse rate limit headers: {e}")


class AdaptiveRateLimiter(RateLimiter):
    """
    Rate limiter that adapts based on server responses.

    Features:
    - Starts conservative and increases rate if no errors
    - Backs off on 429 (Too Many Requests) errors
    - Learns optimal rate over time
    """

    def __init__(self, initial_rate: int = 30, max_rate: int = 120):
        """
        Initialize adaptive rate limiter.

        Args:
            initial_rate: Starting requests per minute (default: 30)
            max_rate: Maximum requests per minute (default: 120)
        """
        super().__init__(initial_rate)
        self.min_rate = 10
        self.max_rate = max_rate
        self.initial_rate = initial_rate

        # Adaptation parameters
        self.success_count = 0
        self.error_count = 0
        self.last_429: Optional[datetime] = None
        self.increase_threshold = 100  # Successes before increasing
        self.decrease_factor = 0.5  # Reduce by 50% on 429
        self.increase_factor = 1.1  # Increase by 10% on success

    def record_success(self) -> None:
        """Record a successful request."""
        self.success_count += 1

        # Consider increasing rate after many successes
        if self.success_count >= self.increase_threshold:
            self._increase_rate()
            self.success_count = 0

    def record_429(self) -> None:
        """Record a 429 (Too Many Requests) error."""
        self.error_count += 1
        self.last_429 = datetime.now(timezone.utc)
        self._decrease_rate()

        # Reset success count on error
        self.success_count = 0

    def _increase_rate(self) -> None:
        """Increase rate limit cautiously."""
        old_rate = self.rate
        self.rate = min(self.max_rate, self.rate * self.increase_factor)
        self.refill_rate = self.rate / 60.0

        if self.rate > old_rate:
            logger.info(f"Increased rate limit: {old_rate:.0f} -> {self.rate:.0f} req/min")

    def _decrease_rate(self) -> None:
        """Decrease rate limit on error."""
        old_rate = self.rate
        self.rate = max(self.min_rate, self.rate * self.decrease_factor)
        self.refill_rate = self.rate / 60.0

        # Also reduce current tokens to prevent immediate retry
        self.tokens = min(self.tokens, self.rate / 10)

        logger.warning(f"Decreased rate limit: {old_rate:.0f} -> {self.rate:.0f} req/min")
