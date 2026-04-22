"""
Request Metrics Mixin - Provides request tracking capabilities for services.

This mixin adds request tracking and metrics collection to any service class.
Tracks request counts, error rates, and response times with full type safety.
"""

import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class RequestMetrics(BaseModel):
    """Metrics for request handling."""

    requests_handled: int = Field(default=0, ge=0, description="Total requests handled")
    error_count: int = Field(default=0, ge=0, description="Total errors encountered")
    average_response_time_ms: float = Field(default=0.0, ge=0.0, description="Average response time in milliseconds")
    success_rate: float = Field(default=100.0, ge=0.0, le=100.0, description="Success rate percentage")
    last_request_time: Optional[datetime] = Field(default=None, description="Timestamp of last request")

    model_config = ConfigDict(extra="forbid")


class RequestMetricsMixin:
    """Mixin class to add request metrics tracking to services.

    Usage:
        class MyService(RequestMetricsMixin, BaseService):
            async def handle_request(self, request):
                request_id = self.track_request_start()
                try:
                    result = await self._process_request(request)
                    self.track_request_end(request_id, success=True)
                    return result
                except Exception as e:
                    self.track_request_end(request_id, success=False)
                    raise
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize request metrics tracking."""
        super().__init__(*args, **kwargs)
        self._requests_handled: int = 0
        self._error_count: int = 0
        self._active_requests: dict[str, float] = {}  # request_id -> start_time
        self._response_times: Deque[float] = deque(maxlen=100)  # Last 100 response times
        self._last_request_time: Optional[datetime] = None

    def track_request_start(self) -> str:
        """Start tracking a new request.

        Returns:
            str: Unique request ID for tracking
        """
        request_id = f"req_{int(time.time() * 1000000)}_{len(self._active_requests)}"
        self._active_requests[request_id] = time.time()
        self._last_request_time = datetime.now(timezone.utc)

        logger.debug(f"Started tracking request {request_id}")
        return request_id

    def track_request_end(self, request_id: str, success: bool = True) -> None:
        """End tracking for a request and update metrics.

        Args:
            request_id: The request ID returned by track_request_start
            success: Whether the request completed successfully
        """
        if request_id not in self._active_requests:
            logger.warning(f"Request {request_id} not found in active requests")
            return

        # Calculate response time
        start_time = self._active_requests.pop(request_id)
        response_time_ms = (time.time() - start_time) * 1000

        # Update metrics
        self._requests_handled += 1
        if not success:
            self._error_count += 1

        # Track response time
        self._response_times.append(response_time_ms)

        logger.debug(
            f"Completed request {request_id} - " f"Success: {success}, Response time: {response_time_ms:.2f}ms"
        )

    def get_request_metrics(self) -> RequestMetrics:
        """Get current request metrics.

        Returns:
            RequestMetrics: Current metrics snapshot
        """
        # Calculate average response time
        avg_response_time = 0.0
        if self._response_times:
            avg_response_time = sum(self._response_times) / len(self._response_times)

        # Calculate success rate
        success_rate = 100.0
        if self._requests_handled > 0:
            success_rate = ((self._requests_handled - self._error_count) / self._requests_handled) * 100

        return RequestMetrics(
            requests_handled=self._requests_handled,
            error_count=self._error_count,
            average_response_time_ms=avg_response_time,
            success_rate=success_rate,
            last_request_time=self._last_request_time,
        )

    def reset_request_metrics(self) -> None:
        """Reset all request metrics to initial state."""
        self._requests_handled = 0
        self._error_count = 0
        self._active_requests.clear()
        self._response_times.clear()
        self._last_request_time = None

        logger.info("Request metrics reset")

    def get_active_request_count(self) -> int:
        """Get the number of currently active requests.

        Returns:
            int: Number of active requests
        """
        return len(self._active_requests)

    def get_response_time_percentile(self, percentile: float) -> float:
        """Get response time at a specific percentile.

        Args:
            percentile: Percentile to calculate (0-100)

        Returns:
            float: Response time in milliseconds at the given percentile
        """
        if not self._response_times:
            return 0.0

        if not 0 <= percentile <= 100:
            raise ValueError("Percentile must be between 0 and 100")

        sorted_times = sorted(self._response_times)
        index = int((percentile / 100) * (len(sorted_times) - 1))
        return sorted_times[index]

    def get_recent_error_rate(self, window_size: int = 10) -> float:
        """Get error rate for recent requests.

        Args:
            window_size: Number of recent requests to consider

        Returns:
            float: Error rate percentage for recent requests
        """
        if self._requests_handled == 0:
            return 0.0

        # For simplicity, we calculate based on overall metrics
        # In a production system, you might track individual request outcomes
        recent_requests = min(window_size, self._requests_handled)
        if recent_requests == 0:
            return 0.0

        # Estimate based on overall error rate
        return (self._error_count / self._requests_handled) * 100


__all__ = ["RequestMetricsMixin", "RequestMetrics"]
