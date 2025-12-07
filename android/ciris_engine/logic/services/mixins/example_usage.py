"""
Example usage of RequestMetricsMixin with a CIRIS service.

This file demonstrates how to integrate the RequestMetricsMixin
with existing CIRIS services following all architectural patterns.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from ciris_engine.logic.services.graph.base import BaseGraphService
from ciris_engine.logic.services.mixins import RequestMetricsMixin
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.buses import MemoryBus
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class MetricsEnabledGraphService(RequestMetricsMixin, BaseGraphService):
    """Example graph service with request metrics tracking.

    This demonstrates how to combine RequestMetricsMixin with existing
    CIRIS service base classes while maintaining proper MRO and patterns.
    """

    def __init__(self, memory_bus: Optional["MemoryBus"] = None, time_service: Optional["TimeServiceProtocol"] = None):
        """Initialize service with metrics tracking."""
        # Initialize both parent classes
        super().__init__(memory_bus=memory_bus, time_service=time_service)

    def get_node_type(self) -> str:
        """Return the node type this service manages."""
        return "example_metrics_node"

    async def store_in_graph(self, node: GraphNode) -> str:
        """Store a node with request tracking.

        Overrides parent method to add metrics tracking.
        """
        request_id = self.track_request_start()

        try:
            # Call parent implementation
            result = await super().store_in_graph(node)

            # Track success
            self.track_request_end(request_id, success=bool(result))

            return result

        except Exception as e:
            # Track failure
            self.track_request_end(request_id, success=False)
            logger.error(f"Failed to store node: {e}")
            raise

    async def query_graph(self, query: MemoryQuery) -> list[GraphNode]:
        """Query the graph with request tracking.

        Overrides parent method to add metrics tracking.
        """
        request_id = self.track_request_start()

        try:
            # Call parent implementation
            results = await super().query_graph(query)

            # Track success
            self.track_request_end(request_id, success=True)

            return results

        except Exception as e:
            # Track failure
            self.track_request_end(request_id, success=False)
            logger.error(f"Failed to query graph: {e}")
            raise

    def get_extended_status(self) -> JSONDict:
        """Get service status including request metrics.

        Extends the base status with request metrics information.
        """
        # Get base status
        base_status = self.get_status()

        # Get request metrics
        metrics = self.get_request_metrics()

        # Combine into extended status
        return {
            "service": base_status.model_dump(),
            "metrics": {
                "requests_handled": metrics.requests_handled,
                "error_count": metrics.error_count,
                "average_response_time_ms": metrics.average_response_time_ms,
                "success_rate": metrics.success_rate,
                "last_request_time": metrics.last_request_time.isoformat() if metrics.last_request_time else None,
                "active_requests": self.get_active_request_count(),
                "p95_response_time_ms": self.get_response_time_percentile(95),
                "recent_error_rate": self.get_recent_error_rate(window_size=20),
            },
        }


# Example 2: Adding metrics to a communication adapter
class MetricsEnabledAdapter:
    """Example of adding metrics to a communication adapter."""

    def __init__(self) -> None:
        # Manually compose the mixin since adapters might not use inheritance
        self._metrics = RequestMetricsMixin()

    async def send_message(self, channel: str, content: str) -> bool:
        """Send a message with metrics tracking."""
        request_id = self._metrics.track_request_start()

        try:
            # Simulate sending message
            await self._do_send(channel, content)

            self._metrics.track_request_end(request_id, success=True)
            return True

        except Exception as e:
            self._metrics.track_request_end(request_id, success=False)
            logger.error(f"Failed to send message: {e}")
            return False

    async def _do_send(self, channel: str, content: str) -> None:
        """Actual message sending logic."""
        # Implementation would go here
        pass

    def get_metrics(self) -> JSONDict:
        """Get adapter metrics."""
        metrics = self._metrics.get_request_metrics()
        return {
            "messages_sent": metrics.requests_handled,
            "send_failures": metrics.error_count,
            "average_send_time_ms": metrics.average_response_time_ms,
            "delivery_rate": metrics.success_rate,
        }


# Example 3: Using metrics in an API endpoint
async def api_endpoint_with_metrics(service: MetricsEnabledGraphService) -> JSONDict:
    """Example API endpoint that exposes service metrics."""

    # Get extended status including metrics
    status = service.get_extended_status()

    # Extract nested dicts with proper typing
    service_dict = get_dict(status, "service", {})
    metrics_dict = get_dict(status, "metrics", {})

    # Could return this in an API response
    return {
        "healthy": service_dict.get("healthy"),
        "performance": {
            "avg_response_ms": metrics_dict.get("average_response_time_ms"),
            "p95_response_ms": metrics_dict.get("p95_response_time_ms"),
            "success_rate": metrics_dict.get("success_rate"),
            "active_requests": metrics_dict.get("active_requests"),
        },
        "load": {
            "total_requests": metrics_dict.get("requests_handled"),
            "error_count": metrics_dict.get("error_count"),
            "recent_error_rate": metrics_dict.get("recent_error_rate"),
        },
    }


# Example 4: Monitoring and alerting
async def check_service_health(service: MetricsEnabledGraphService) -> list[str]:
    """Check service health based on metrics."""
    alerts = []
    metrics = service.get_request_metrics()

    # Check error rate
    if metrics.success_rate < 95.0:
        alerts.append(f"High error rate: {100 - metrics.success_rate:.1f}%")

    # Check response time
    p95 = service.get_response_time_percentile(95)
    if p95 > 1000:  # 1 second
        alerts.append(f"Slow response times: p95={p95:.0f}ms")

    # Check recent errors
    recent_error_rate = service.get_recent_error_rate(window_size=10)
    if recent_error_rate > 20:
        alerts.append(f"Recent error spike: {recent_error_rate:.1f}%")

    return alerts
