from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Deque, Dict, Optional, Tuple
from uuid import uuid4

from ciris_engine.logic.persistence.models.correlations import add_correlation
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    MetricData,
    ServiceCorrelation,
    ServiceCorrelationStatus,
)
from ciris_engine.schemas.types import JSONDict

from .security import SecurityFilter

logger = logging.getLogger(__name__)


class BasicTelemetryCollector(BaseService):
    """Collects and exposes basic telemetry for agent introspection."""

    def __init__(
        self,
        buffer_size: int = 1000,
        security_filter: SecurityFilter | None = None,
        time_service: TimeService | None = None,
    ) -> None:
        # Initialize BaseService with time_service
        super().__init__(time_service=time_service, service_name="BasicTelemetryCollector")
        self.buffer_size = buffer_size
        self._history: Dict[str, Deque[Tuple[datetime, float]]] = defaultdict(lambda: deque(maxlen=self.buffer_size))
        self._filter = security_filter or SecurityFilter()
        # Use the time_service from BaseService instead of creating a new one
        if not self._time_service:
            self._time_service = TimeService()
        self.start_time = self._time_service.now()
        self._pending_stores: set[asyncio.Task[Any]] = set()
        # Note: _started is now provided by BaseService

    async def start(self) -> None:
        await super().start()
        logger.info("Telemetry service started")

    async def stop(self) -> None:
        """Stop the service and ensure all metrics are persisted."""
        await super().stop()

        if self._pending_stores:
            logger.info(f"Waiting for {len(self._pending_stores)} pending metric storage tasks...")
            try:
                await asyncio.wait_for(asyncio.gather(*self._pending_stores, return_exceptions=True), timeout=30.0)
                logger.info("All metric storage tasks completed")
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for metric storage - some metrics may be lost")

        logger.info("Telemetry service stopped")

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        if len(self._pending_stores) > 100:
            logger.warning(f"Telemetry backlog: {len(self._pending_stores)} pending tasks")
            return False
        return await super().is_healthy()

    async def record_metric(  # NOSONAR: Async for future compatibility with async backends
        self,
        metric_name: str,
        value: float = 1.0,
        tags: Optional[Dict[str, str]] = None,
        path_type: Optional[str] = None,  # hot, cold, critical
        source_module: Optional[str] = None,
    ) -> None:
        # FAIL FAST: TimeService must be initialized
        assert self._time_service is not None, "TimeService not initialized in BasicTelemetryCollector"

        sanitized = self._filter.sanitize(metric_name, value)
        if sanitized is None:
            logger.debug("Metric discarded by security filter: %s", metric_name)
            return
        name, val = sanitized

        # Enhanced metric with tags, timestamp, and hot/cold path info
        timestamp = self._time_service.now()

        # Auto-detect path type based on metric name patterns if not provided
        if path_type is None:
            if any(critical in name for critical in ["error", "critical", "security", "auth", "circuit_breaker"]):
                path_type = "critical"
            elif any(hot in name for hot in ["thought_processing", "handler_invoked", "action_selected", "dma_"]):
                path_type = "hot"
            elif any(cold in name for cold in ["memory_", "persistence_", "context_fetch", "service_lookup"]):
                path_type = "cold"
            else:
                path_type = "normal"

        metric_entry = {
            "timestamp": timestamp,
            "value": float(val),
            "tags": tags or {},
            "path_type": path_type,
            "source_module": source_module or "unknown",
        }

        # Store both simple format for backward compatibility and enhanced format
        self._history[name].append((timestamp, float(val)))

        # Store enhanced metrics in separate history for TSDB capabilities
        if not hasattr(self, "_enhanced_history"):
            self._enhanced_history: Dict[str, Deque[JSONDict]] = defaultdict(lambda: deque(maxlen=self.buffer_size))

        from typing import cast

        self._enhanced_history[name].append(cast(JSONDict, metric_entry))

        # Store metric in TSDB as correlation
        try:
            # Include path_type and source_module in tags instead of metadata
            combined_tags = tags.copy() if tags else {}
            combined_tags["path_type"] = path_type
            combined_tags["source_module"] = source_module or "unknown"

            metric_correlation = ServiceCorrelation(
                correlation_id=str(uuid4()),
                service_type="telemetry",
                handler_name="telemetry_service",
                action_type="record_metric",
                correlation_type=CorrelationType.METRIC_DATAPOINT,
                timestamp=timestamp,
                metric_data=MetricData(
                    metric_name=name, metric_value=float(val), metric_unit="count", metric_type="gauge"  # Default unit
                ),
                tags=combined_tags,
                status=ServiceCorrelationStatus.COMPLETED,
                retention_policy=self._get_retention_policy(path_type),
                created_at=timestamp,
                updated_at=timestamp,
            )

            # Store asynchronously without blocking metric recording
            task = asyncio.create_task(self._store_metric_correlation(metric_correlation))
            self._pending_stores.add(task)
            task.add_done_callback(lambda t: self._pending_stores.discard(t))
        except Exception as e:
            logger.error(f"Failed to create metric correlation: {e}")

    async def _store_metric_correlation(self, correlation: ServiceCorrelation) -> None:
        """Store metric correlation in TSDB asynchronously."""
        try:
            add_correlation(correlation, self._time_service)
        except Exception as e:
            logger.error(f"Failed to store metric correlation in TSDB: {e}")

    async def update_system_snapshot(self, snapshot: SystemSnapshot) -> None:
        """Update SystemSnapshot.telemetry with recent metrics."""
        # FAIL FAST: TimeService must be initialized
        assert self._time_service is not None, "TimeService not initialized in BasicTelemetryCollector"

        now = self._time_service.now()
        cutoff_24h = now - timedelta(hours=24)
        cutoff_1h = now - timedelta(hours=1)

        # Create telemetry summary
        from ciris_engine.schemas.runtime.system_context import TelemetrySummary

        telemetry = TelemetrySummary(
            window_start=cutoff_24h, window_end=now, uptime_seconds=(now - self.start_time).total_seconds()
        )

        # Count metrics for different time windows
        for name, records in self._history.items():
            # Filter to 24h window and clean up old records
            filtered_records = [r for r in records if r[0] > cutoff_24h]
            self._history[name] = deque(filtered_records, maxlen=self.buffer_size)

            # Count 24h metrics
            count_24h = len(filtered_records)
            # Count current hour metrics
            count_1h = len([r for r in filtered_records if r[0] > cutoff_1h])

            # Update telemetry based on metric name
            if name == "message_processed":
                telemetry.messages_processed_24h = count_24h
                telemetry.messages_current_hour = count_1h
            elif name == "error":
                telemetry.errors_24h = count_24h
                telemetry.errors_current_hour = count_1h
            elif name == "thought_processed":
                telemetry.thoughts_processed_24h = count_24h
                telemetry.thoughts_current_hour = count_1h
            elif name == "task_completed":
                telemetry.tasks_completed_24h = count_24h

            # Track service-specific metrics
            if name.startswith("service_"):
                service_name = name.replace("service_", "").replace("_call", "")
                telemetry.service_calls[service_name] = count_24h

        # Calculate rates
        if telemetry.messages_processed_24h > 0:
            telemetry.error_rate_percent = (telemetry.errors_24h / telemetry.messages_processed_24h) * 100

        # Update snapshot
        snapshot.telemetry_summary = telemetry

    def _get_retention_policy(self, path_type: Optional[str]) -> str:
        """Determine retention policy based on path type."""
        if path_type == "critical":
            return "raw"  # Keep all critical metrics
        elif path_type == "hot":
            return "raw"  # Keep hot path metrics for performance analysis
        elif path_type == "cold":
            return "aggregated"  # Aggregate cold path metrics
        else:
            return "aggregated"  # Default to aggregated

    # Required abstract methods from BaseService

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.TELEMETRY

    def _get_actions(self) -> list[str]:
        """Get list of actions this service provides."""
        return ["record_metric", "update_system_snapshot", "get_metrics"]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # TimeService is our only dependency and it's optional
        # (we create one if not provided)
        return True
