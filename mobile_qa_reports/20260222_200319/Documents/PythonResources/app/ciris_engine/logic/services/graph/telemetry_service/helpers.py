"""
Helper functions for telemetry service refactoring.

These break down the complex get_telemetry_summary method into focused,
testable components. All functions fail fast and loud - no fallback data.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union

from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

from ciris_engine.logic.services.graph.telemetry_service.exceptions import (
    MemoryBusUnavailableError,
    MetricCollectionError,
    NoThoughtDataError,
    QueueStatusUnavailableError,
    RuntimeControlBusUnavailableError,
    ServiceStartTimeUnavailableError,
    ThoughtDepthQueryError,
    UnknownMetricTypeError,
)
from ciris_engine.schemas.runtime.system_context import ContinuitySummary, TelemetrySummary
from ciris_engine.schemas.services.graph.telemetry import MetricAggregates, MetricRecord

# TypeVar for summary cache
SummaryType = TypeVar("SummaryType", TelemetrySummary, ContinuitySummary)

if TYPE_CHECKING:
    from ciris_engine.logic.buses.memory_bus import MemoryBus
    from ciris_engine.logic.buses.runtime_control_bus import RuntimeControlBus
    from ciris_engine.logic.services.graph.telemetry_service.service import GraphTelemetryService
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

# Metric types to query - moved from inline definition
METRIC_TYPES = [
    ("llm.tokens.total", "tokens"),
    ("llm_tokens_used", "tokens"),  # Legacy metric name
    ("llm.tokens.input", "tokens"),
    ("llm.tokens.output", "tokens"),
    ("llm.cost.cents", "cost"),
    ("llm.environmental.carbon_grams", "carbon"),
    ("llm.environmental.energy_kwh", "energy"),
    ("llm.latency.ms", "latency"),
    ("thought_processing_completed", "thoughts"),
    ("thought_processing_started", "thoughts"),
    ("action_selected_task_complete", "tasks"),
    ("handler_invoked_total", "messages"),
    ("error.occurred", "errors"),
]


# ============================================================================
# METRIC COLLECTION HELPERS
# ============================================================================


async def collect_metric_aggregates(
    telemetry_service: "GraphTelemetryService",
    metric_types: List[Tuple[str, str]],
    window_start_24h: datetime,
    window_start_1h: datetime,
    window_end: datetime,
) -> MetricAggregates:
    """Collect and aggregate metrics across time windows.

    Args:
        telemetry_service: The telemetry service instance
        metric_types: List of (metric_name, metric_type) tuples to query
        window_start_24h: Start of 24-hour window
        window_start_1h: Start of 1-hour window
        window_end: End of both windows

    Returns:
        MetricAggregates schema with all collected metrics

    Raises:
        MetricCollectionError: If metric collection fails
        InvalidMetricDataError: If metric data is invalid
    """
    aggregates = MetricAggregates()

    try:
        for metric_name, metric_type in metric_types:
            # Get 24h data
            day_metrics: List[MetricRecord] = await telemetry_service.query_metrics(
                metric_name=metric_name, start_time=window_start_24h, end_time=window_end
            )

            for metric in day_metrics:
                # Aggregate into appropriate counter
                aggregate_metric_by_type(
                    metric_type, metric.value, metric.timestamp, metric.tags, aggregates, window_start_1h
                )

        return aggregates

    except Exception as e:
        raise MetricCollectionError(f"Failed to collect metric aggregates: {e}") from e


def _update_windowed_metric(
    aggregates: MetricAggregates,
    field_24h: str,
    field_1h: str,
    value: float,
    in_1h_window: bool,
    converter: Callable[[float], Union[int, float]] = float,
) -> None:
    """Update a metric with both 24h and 1h windows.

    Args:
        aggregates: MetricAggregates object to update
        field_24h: Name of 24h field to update
        field_1h: Name of 1h field to update
        value: Value to add
        in_1h_window: Whether metric is in 1h window
        converter: Function to convert value (int or float)
    """
    setattr(aggregates, field_24h, getattr(aggregates, field_24h) + converter(value))
    if in_1h_window:
        setattr(aggregates, field_1h, getattr(aggregates, field_1h) + converter(value))


def _handle_tokens_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle tokens metric aggregation."""
    _update_windowed_metric(aggregates, "tokens_24h", "tokens_1h", value, in_1h_window, int)


def _handle_cost_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle cost metric aggregation."""
    _update_windowed_metric(aggregates, "cost_24h_cents", "cost_1h_cents", value, in_1h_window, float)


def _handle_carbon_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle carbon metric aggregation."""
    _update_windowed_metric(aggregates, "carbon_24h_grams", "carbon_1h_grams", value, in_1h_window, float)


def _handle_energy_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle energy metric aggregation."""
    _update_windowed_metric(aggregates, "energy_24h_kwh", "energy_1h_kwh", value, in_1h_window, float)


def _handle_messages_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle messages metric aggregation."""
    _update_windowed_metric(aggregates, "messages_24h", "messages_1h", value, in_1h_window, int)


def _handle_thoughts_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool) -> None:
    """Handle thoughts metric aggregation."""
    _update_windowed_metric(aggregates, "thoughts_24h", "thoughts_1h", value, in_1h_window, int)


def _handle_tasks_metric(aggregates: MetricAggregates, value: float) -> None:
    """Handle tasks metric aggregation (24h only, no 1h tracking)."""
    aggregates.tasks_24h += int(value)


def _handle_errors_metric(aggregates: MetricAggregates, value: float, in_1h_window: bool, tags: Dict[str, str]) -> None:
    """Handle errors metric aggregation."""
    _update_windowed_metric(aggregates, "errors_24h", "errors_1h", value, in_1h_window, int)
    # Track errors by service
    service = tags.get("service", "unknown")
    aggregates.service_errors[service] = aggregates.service_errors.get(service, 0) + 1


def _handle_latency_metric(aggregates: MetricAggregates, value: float, tags: Dict[str, str]) -> None:
    """Handle latency metric aggregation (service-level, no time windowing)."""
    service = tags.get("service", "unknown")
    if service not in aggregates.service_latency:
        aggregates.service_latency[service] = []
    aggregates.service_latency[service].append(float(value))


# Handler type definition
MetricHandlerFunc = Callable[[MetricAggregates, float, bool, Dict[str, str]], None]

# Metric type dispatch table
_METRIC_HANDLERS: Dict[str, MetricHandlerFunc] = {
    "tokens": lambda agg, val, win, tags: _handle_tokens_metric(agg, val, win),
    "cost": lambda agg, val, win, tags: _handle_cost_metric(agg, val, win),
    "carbon": lambda agg, val, win, tags: _handle_carbon_metric(agg, val, win),
    "energy": lambda agg, val, win, tags: _handle_energy_metric(agg, val, win),
    "messages": lambda agg, val, win, tags: _handle_messages_metric(agg, val, win),
    "thoughts": lambda agg, val, win, tags: _handle_thoughts_metric(agg, val, win),
    "tasks": lambda agg, val, win, tags: _handle_tasks_metric(agg, val),
    "errors": lambda agg, val, win, tags: _handle_errors_metric(agg, val, win, tags),
    "latency": lambda agg, val, win, tags: _handle_latency_metric(agg, val, tags),
}


def aggregate_metric_by_type(
    metric_type: str,
    value: float,
    timestamp: datetime,
    tags: Dict[str, str],
    aggregates: MetricAggregates,
    window_start_1h: datetime,
) -> None:
    """Aggregate a single metric value into the appropriate counters.

    Args:
        metric_type: Type of metric (tokens, cost, carbon, etc.)
        value: Numeric value from metric
        timestamp: When the metric occurred
        tags: Metric tags (service, etc.)
        aggregates: MetricAggregates object to update (mutated)
        window_start_1h: Start of 1-hour window for filtering

    Raises:
        UnknownMetricTypeError: If metric_type is not recognized
    """
    # Check if timestamp is in 1h window
    in_1h_window = timestamp >= window_start_1h

    # Dispatch to appropriate handler
    handler = _METRIC_HANDLERS.get(metric_type)
    if not handler:
        raise UnknownMetricTypeError(f"Unknown metric type: {metric_type}")

    handler(aggregates, value, in_1h_window, tags)

    # Track service calls
    if "service" in tags:
        service = tags["service"]
        aggregates.service_calls[service] = aggregates.service_calls.get(service, 0) + 1


# ============================================================================
# EXTERNAL DATA COLLECTION HELPERS
# ============================================================================


async def get_average_thought_depth(
    memory_bus: Optional["MemoryBus"],
    window_start: datetime,
) -> float:
    """Get average thought depth from the last 24 hours.

    Args:
        memory_bus: Memory bus to access persistence
        window_start: Start of time window

    Returns:
        Average thought depth (must be valid positive number)

    Raises:
        MemoryBusUnavailableError: If memory bus not available
        ThoughtDepthQueryError: If database query fails
        NoThoughtDataError: If no thought data available in window
    """
    if not memory_bus:
        raise MemoryBusUnavailableError("Memory bus is not available")

    try:
        from ciris_engine.logic.persistence import get_db_connection

        # Get the memory service to access its db_path
        memory_service = await memory_bus.get_service(handler_name="telemetry_service")
        if not memory_service:
            raise MemoryBusUnavailableError("Memory service not found on memory bus")

        db_path = getattr(memory_service, "db_path", None)
        if not db_path:
            raise ThoughtDepthQueryError("Memory service has no db_path attribute")

        from ciris_engine.logic.persistence.db.dialect import get_adapter

        adapter = get_adapter()

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            # Use window_start parameter for consistent timing with other telemetry calculations
            # Use dialect-appropriate placeholder
            sql = f"""
                SELECT AVG(thought_depth) as avg_depth
                FROM thoughts
                WHERE created_at >= {adapter.placeholder()}
            """
            cursor.execute(sql, (window_start.isoformat(),))
            result = cursor.fetchone()

            # Handle both dict (PostgreSQL RealDictCursor/SQLite Row) and tuple results
            if result:
                if isinstance(result, dict):
                    avg_depth = result.get("avg_depth")
                elif hasattr(result, "keys"):
                    # SQLite Row or dict-like object
                    avg_depth = result["avg_depth"]
                else:
                    # Tuple result - first column is avg_depth
                    avg_depth = result[0] if result else None

                if avg_depth is not None:
                    return float(avg_depth)

            raise NoThoughtDataError("No thought data available in the last 24 hours")

    except NoThoughtDataError:
        raise  # Re-raise as-is
    except Exception as e:
        raise ThoughtDepthQueryError(f"Failed to query thought depth: {e}") from e


async def get_queue_saturation(
    runtime_control_bus: Optional["RuntimeControlBus"],
) -> float:
    """Get current processor queue saturation (0.0-1.0).

    Args:
        runtime_control_bus: Runtime control bus to access queue status

    Returns:
        Queue saturation ratio between 0.0 and 1.0

    Raises:
        RuntimeControlBusUnavailableError: If runtime control bus not available
        QueueStatusUnavailableError: If queue status cannot be retrieved
    """
    if not runtime_control_bus:
        raise RuntimeControlBusUnavailableError("Runtime control bus is not available")

    try:
        runtime_control = await runtime_control_bus.get_service(handler_name="telemetry_service")
        if not runtime_control:
            raise RuntimeControlBusUnavailableError("Runtime control service not found on bus")

        processor_queue_status = await runtime_control.get_processor_queue_status()
        if not processor_queue_status:
            raise QueueStatusUnavailableError("get_processor_queue_status returned None")

        if processor_queue_status.max_size <= 0:
            raise QueueStatusUnavailableError(f"Invalid max_size: {processor_queue_status.max_size}")

        queue_saturation = processor_queue_status.queue_size / processor_queue_status.max_size
        # Clamp to 0-1 range
        return float(min(1.0, max(0.0, queue_saturation)))

    except (RuntimeControlBusUnavailableError, QueueStatusUnavailableError):
        raise  # Re-raise as-is
    except Exception as e:
        raise QueueStatusUnavailableError(f"Failed to get queue saturation: {e}") from e


def get_service_uptime(
    start_time: Optional[datetime],
    now: datetime,
) -> float:
    """Get service uptime in seconds.

    Args:
        start_time: When the service started (or None)
        now: Current time

    Returns:
        Uptime in seconds

    Raises:
        ServiceStartTimeUnavailableError: If start_time is None
    """
    if start_time is None:
        raise ServiceStartTimeUnavailableError("Service start_time has not been set")

    return (now - start_time).total_seconds()


# ============================================================================
# CALCULATION HELPERS
# ============================================================================


def calculate_error_rate(
    errors_24h: int,
    total_operations: int,
) -> float:
    """Calculate error rate percentage.

    Args:
        errors_24h: Number of errors in 24h window
        total_operations: Total operations (messages + thoughts + tasks)

    Returns:
        Error rate as percentage (0.0-100.0)
    """
    if total_operations == 0:
        return 0.0
    return (errors_24h / total_operations) * 100.0


def calculate_average_latencies(
    service_latency: Dict[str, List[float]],
) -> Dict[str, float]:
    """Calculate average latency per service.

    Args:
        service_latency: Map of service name to list of latency values

    Returns:
        Map of service name to average latency in ms
    """
    result = {}
    for service, latencies in service_latency.items():
        if latencies:
            result[service] = sum(latencies) / len(latencies)
    return result


# ============================================================================
# CACHE HELPERS
# ============================================================================


def check_summary_cache(
    cache: Dict[str, Tuple[datetime, Any]],
    cache_key: str,
    now: datetime,
    ttl_seconds: int,
) -> Optional[Any]:
    """Check if cached summary is still valid.

    Args:
        cache: Summary cache dictionary
        cache_key: Key to look up in cache
        now: Current time
        ttl_seconds: Cache TTL in seconds

    Returns:
        Cached summary (TelemetrySummary or ContinuitySummary) if valid, None otherwise
    """
    if cache_key in cache:
        cached_time, cached_summary = cache[cache_key]
        if (now - cached_time).total_seconds() < ttl_seconds:
            return cached_summary
    return None


def store_summary_cache(
    cache: Dict[str, Tuple[datetime, Any]],
    cache_key: str,
    now: datetime,
    summary: Any,
) -> None:
    """Store summary in cache.

    Args:
        cache: Summary cache dictionary (mutated)
        cache_key: Key to store under
        now: Current time
        summary: Summary to cache
    """
    cache[cache_key] = (now, summary)


# ============================================================================
# SCHEMA BUILDERS
# ============================================================================


def _extract_service_stats_cb_data(stats: JSONDict) -> "CircuitBreakerState":
    """Extract circuit breaker data from service stats dict.

    Args:
        stats: Service stats dict containing circuit_breaker_state

    Returns:
        CircuitBreakerState with state and metrics
    """
    # Import at runtime to avoid circular dependency
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    return CircuitBreakerState(
        state=stats.get("circuit_breaker_state", "unknown"),
        total_requests=stats.get("total_requests", 0),
        failed_requests=stats.get("failed_requests", 0),
        failure_rate=stats.get("failure_rate", "0.00%"),
        consecutive_failures=stats.get("consecutive_failures", 0),
        failure_count=stats.get("consecutive_failures", 0),
        success_count=0,
    )


def _extract_direct_cb_data(cb: Any) -> "CircuitBreakerState":
    """Extract circuit breaker data from CircuitBreaker object.

    Args:
        cb: CircuitBreaker instance

    Returns:
        CircuitBreakerState with state and counts
    """
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    return CircuitBreakerState(
        state=str(cb.state) if hasattr(cb, "state") else "unknown",
        failure_count=cb.failure_count if hasattr(cb, "failure_count") else 0,
        success_count=cb.success_count if hasattr(cb, "success_count") else 0,
        total_requests=0,
        failed_requests=0,
        consecutive_failures=cb.failure_count if hasattr(cb, "failure_count") else 0,
        failure_rate="0.00%",
    )


def _collect_from_service_stats(bus: Any) -> Dict[str, "CircuitBreakerState"]:
    """Collect circuit breaker data from bus.get_service_stats().

    Args:
        bus: Bus instance with get_service_stats method

    Returns:
        Dict mapping service names to their circuit breaker state
    """
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    cb_data: Dict[str, CircuitBreakerState] = {}

    try:
        service_stats = bus.get_service_stats()
        if not isinstance(service_stats, dict):
            return cb_data

        for svc_name, stats in service_stats.items():
            if isinstance(stats, dict) and "circuit_breaker_state" in stats:
                cb_data[svc_name] = _extract_service_stats_cb_data(stats)

    except Exception:
        # Silently skip buses that fail to provide stats
        pass

    return cb_data


def _collect_from_direct_cb_attribute(
    bus: Any, existing_data: Dict[str, "CircuitBreakerState"]
) -> Dict[str, "CircuitBreakerState"]:
    """Collect circuit breaker data from bus.circuit_breakers attribute.

    Args:
        bus: Bus instance with circuit_breakers attribute
        existing_data: Already collected CB data (don't override these)

    Returns:
        Dict mapping service names to their circuit breaker state
    """
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    cb_data: Dict[str, CircuitBreakerState] = {}

    try:
        circuit_breakers = bus.circuit_breakers
        if not isinstance(circuit_breakers, dict):
            return cb_data

        for cb_name, cb in circuit_breakers.items():
            if cb_name not in existing_data:  # Don't override if already collected
                cb_data[cb_name] = _extract_direct_cb_data(cb)

    except Exception:
        # Silently skip
        pass

    return cb_data


def _collect_from_single_bus(bus: Any) -> Dict[str, "CircuitBreakerState"]:
    """Collect circuit breaker data from a single bus.

    Args:
        bus: Bus instance to collect from

    Returns:
        Dict mapping service names to their circuit breaker state
    """
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    cb_data: Dict[str, CircuitBreakerState] = {}

    # Try get_service_stats first
    if hasattr(bus, "get_service_stats"):
        logger.debug("[CB COLLECT] Bus has get_service_stats method")
        cb_data.update(_collect_from_service_stats(bus))
        logger.debug(f"[CB COLLECT] Collected {len(cb_data)} CBs from service_stats")

    # Also check direct circuit_breakers attribute
    if hasattr(bus, "circuit_breakers"):
        cb_attr = getattr(bus, "circuit_breakers", {})
        logger.debug(
            f"[CB COLLECT] Bus has circuit_breakers attribute with {len(cb_attr) if isinstance(cb_attr, dict) else 0} entries"
        )
        cb_data.update(_collect_from_direct_cb_attribute(bus, cb_data))
        logger.debug(f"[CB COLLECT] Total {len(cb_data)} CBs after checking circuit_breakers attribute")

    return cb_data


def collect_circuit_breaker_state(runtime: Any) -> Dict[str, "CircuitBreakerState"]:
    """Collect circuit breaker state from all buses.

    Walks through all buses (LLM, Memory, Communication, Tool, Wise, RuntimeControl)
    via the runtime's bus_manager and collects their circuit breaker states.

    Args:
        runtime: Runtime instance with bus_manager attribute

    Returns:
        Dict mapping service names to their circuit breaker state
    """
    from ciris_engine.schemas.services.graph.telemetry import CircuitBreakerState

    circuit_breaker_data: Dict[str, CircuitBreakerState] = {}

    if not runtime:
        logger.debug("[CB COLLECT] No runtime provided")
        return circuit_breaker_data

    try:
        bus_manager = getattr(runtime, "bus_manager", None)
        if not bus_manager:
            logger.debug(f"[CB COLLECT] Runtime has no bus_manager (type: {type(runtime).__name__})")
            return circuit_breaker_data

        # List of bus attributes to check
        bus_names = ["llm", "memory", "communication", "wise", "tool", "runtime_control"]

        for bus_name in bus_names:
            bus = getattr(bus_manager, bus_name, None)
            if bus:
                logger.debug(f"[CB COLLECT] Collecting from {bus_name} bus ({type(bus).__name__})")
                bus_data = _collect_from_single_bus(bus)
                if bus_data:
                    logger.debug(f"[CB COLLECT] Found {len(bus_data)} circuit breakers in {bus_name} bus")
                circuit_breaker_data.update(bus_data)
            else:
                logger.debug(f"[CB COLLECT] No {bus_name} bus in bus_manager")

        logger.debug(f"[CB COLLECT] Total circuit breakers collected: {len(circuit_breaker_data)}")

    except Exception as e:
        # If anything fails, return whatever we collected so far
        logger.warning(f"[CB COLLECT] Error collecting circuit breakers: {e}")

    return circuit_breaker_data


def build_telemetry_summary(
    window_start: datetime,
    window_end: datetime,
    uptime_seconds: float,
    aggregates: MetricAggregates,
    error_rate: float,
    avg_thought_depth: float,
    queue_saturation: float,
    service_latency_ms: Dict[str, float],
    circuit_breaker: Optional[Dict[str, "CircuitBreakerState"]] = None,
) -> TelemetrySummary:
    """Build TelemetrySummary from collected data.

    Args:
        window_start: Start of time window
        window_end: End of time window
        uptime_seconds: Service uptime
        aggregates: Collected metric aggregates
        error_rate: Calculated error rate percentage
        avg_thought_depth: Average thought depth
        queue_saturation: Queue saturation ratio
        service_latency_ms: Service latency map
        circuit_breaker: Circuit breaker state across all services

    Returns:
        Validated TelemetrySummary schema
    """
    return TelemetrySummary(
        window_start=window_start,
        window_end=window_end,
        uptime_seconds=uptime_seconds,
        messages_processed_24h=aggregates.messages_24h,
        thoughts_processed_24h=aggregates.thoughts_24h,
        tasks_completed_24h=aggregates.tasks_24h,
        errors_24h=aggregates.errors_24h,
        messages_current_hour=aggregates.messages_1h,
        thoughts_current_hour=aggregates.thoughts_1h,
        errors_current_hour=aggregates.errors_1h,
        service_calls=aggregates.service_calls,
        service_errors=aggregates.service_errors,
        service_latency_ms=service_latency_ms,
        tokens_last_hour=float(aggregates.tokens_1h),
        cost_last_hour_cents=aggregates.cost_1h_cents,
        carbon_last_hour_grams=aggregates.carbon_1h_grams,
        energy_last_hour_kwh=aggregates.energy_1h_kwh,
        tokens_24h=float(aggregates.tokens_24h),
        cost_24h_cents=aggregates.cost_24h_cents,
        carbon_24h_grams=aggregates.carbon_24h_grams,
        energy_24h_kwh=aggregates.energy_24h_kwh,
        error_rate_percent=error_rate,
        avg_thought_depth=avg_thought_depth,
        queue_saturation=queue_saturation,
        circuit_breaker=circuit_breaker,
    )


# =============================================================================
# QUERY_METRICS HELPERS (CC 22 → 6 reduction)
# =============================================================================


def calculate_query_time_window(start_time: Optional[datetime], end_time: Optional[datetime], now: datetime) -> int:
    """
    Calculate hours for query time window.

    Args:
        start_time: Optional start of time range
        end_time: Optional end of time range
        now: Current time

    Returns:
        Number of hours for the query window (default 24)
    """
    if start_time and end_time:
        return int((end_time - start_time).total_seconds() / 3600)
    elif start_time:
        return int((now - start_time).total_seconds() / 3600)
    return 24  # Default


def filter_by_metric_name(data: object, metric_name: str) -> bool:
    """
    Check if timeseries data matches the requested metric name.

    Args:
        data: Timeseries data point with metric_name attribute
        metric_name: Name of metric to match

    Returns:
        True if data matches metric name
    """
    return getattr(data, "metric_name", None) == metric_name


def filter_by_tags(data: object, tags: Optional[Dict[str, str]]) -> bool:
    """
    Check if timeseries data matches all required tags.

    Args:
        data: Timeseries data point with tags or labels attribute
        tags: Optional dictionary of tags to match

    Returns:
        True if data matches all tags (or tags is None)
    """
    if not tags:
        return True

    # Check both 'tags' and 'labels' attributes
    # Note: 'tags' may be a list, 'labels' is the dict we want for key-value filtering
    data_tags = getattr(data, "tags", None)
    if not isinstance(data_tags, dict):
        data_tags = getattr(data, "labels", None)
    if not isinstance(data_tags, dict):
        data_tags = {}

    return all(data_tags.get(k) == v for k, v in tags.items())


def filter_by_time_range(data: object, start_time: Optional[datetime], end_time: Optional[datetime]) -> bool:
    """
    Check if timeseries data timestamp is within the specified range.

    Args:
        data: Timeseries data point with timestamp/start_time attribute
        start_time: Optional start of time range
        end_time: Optional end of time range

    Returns:
        True if timestamp is within range (or no range specified)
    """
    # Try timestamp first, fall back to start_time (used by TSDBGraphNode)
    timestamp = getattr(data, "timestamp", None) or getattr(data, "start_time", None)
    if not timestamp:
        return False

    if start_time and timestamp < start_time:
        return False

    if end_time and timestamp > end_time:
        return False

    return True


def convert_to_metric_record(data: object) -> Optional[MetricRecord]:
    """
    Convert timeseries data to typed MetricRecord.

    Args:
        data: Timeseries data point

    Returns:
        MetricRecord if data is valid, None otherwise
    """
    metric_name = getattr(data, "metric_name", None)
    value = getattr(data, "value", None)
    # Try timestamp first, fall back to start_time (used by TSDBGraphNode)
    timestamp = getattr(data, "timestamp", None) or getattr(data, "start_time", None)

    # Validate required fields
    if not (metric_name and value is not None and timestamp):
        return None

    # Check both 'tags' and 'labels' attributes
    # Note: 'tags' may be a list, 'labels' is the dict we want for metadata
    tags = getattr(data, "tags", None)
    if not isinstance(tags, dict):
        tags = getattr(data, "labels", None)
    if not isinstance(tags, dict):
        tags = {}

    return MetricRecord(
        metric_name=metric_name,
        value=value,
        timestamp=timestamp,
        tags=tags,
    )


# =============================================================================
# _TRY_COLLECT_METRICS HELPERS (CC 19 → 6 reduction)
# =============================================================================


def should_retry_metric_collection(attempt: int, max_retries: int) -> bool:
    """
    Determine if metric collection should be retried.

    Args:
        attempt: Current attempt number (0-indexed)
        max_retries: Maximum number of retries allowed

    Returns:
        True if should retry
    """
    return attempt < max_retries


def calculate_retry_delay(attempt: int, base_delay: float = 0.1) -> float:
    """
    Calculate exponential backoff delay for retry.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds

    Returns:
        Delay in seconds
    """
    return float(base_delay * (2**attempt))


def validate_collected_metrics(metrics: object) -> bool:
    """
    Validate that collected metrics are in expected format.

    Args:
        metrics: Metrics data to validate

    Returns:
        True if metrics are valid
    """
    if metrics is None:
        return False

    # Check if it's a dictionary with expected structure
    if isinstance(metrics, dict):
        return True

    # Check if it's an object with attributes
    if hasattr(metrics, "__dict__"):
        return True

    return False


# =============================================================================
# COLLECT_FROM_ADAPTER_INSTANCES HELPERS (CC 19 → 6 reduction)
# =============================================================================


def extract_adapter_name(adapter: object) -> str:
    """
    Extract adapter name from adapter instance.

    Args:
        adapter: Adapter instance

    Returns:
        Adapter name string
    """
    if hasattr(adapter, "adapter_name"):
        return str(adapter.adapter_name)
    elif hasattr(adapter, "name"):
        return str(adapter.name)
    elif hasattr(adapter, "__class__"):
        return adapter.__class__.__name__
    return "unknown_adapter"


def is_adapter_healthy(adapter: object) -> bool:
    """
    Check if adapter is in healthy state for metrics collection.

    Args:
        adapter: Adapter instance

    Returns:
        True if adapter is healthy
    """
    # Check if adapter has status attribute
    if hasattr(adapter, "status"):
        status = adapter.status
        if hasattr(status, "value"):
            return bool(status.value == "running")
        return str(status).lower() == "running"

    # If no status, assume healthy
    return True


async def collect_metrics_from_single_adapter(adapter: object) -> Optional[Dict[str, float]]:
    """
    Collect metrics from a single adapter instance.

    Args:
        adapter: Adapter instance

    Returns:
        Metrics dictionary or None if collection failed
    """
    try:
        if hasattr(adapter, "get_metrics"):
            metrics = await adapter.get_metrics()
            return metrics if isinstance(metrics, dict) else None
        return None
    except Exception:
        return None


def aggregate_adapter_metrics(collected_metrics: List[Dict[str, float]]) -> Dict[str, float]:
    """
    Aggregate metrics from multiple adapters.

    Args:
        collected_metrics: List of metrics dictionaries

    Returns:
        Aggregated metrics dictionary
    """
    aggregated: Dict[str, float] = {}

    for metrics in collected_metrics:
        if not metrics:
            continue

        for key, value in metrics.items():
            if key not in aggregated:
                aggregated[key] = value
            elif isinstance(value, (int, float)) and isinstance(aggregated[key], (int, float)):
                # Sum numeric values
                aggregated[key] = aggregated[key] + value

    return aggregated


# =============================================================================
# _GENERATE_SEMANTIC_SERVICE_NAME HELPERS (CC 16 → 6 reduction)
# =============================================================================


# Service name mapping table
SERVICE_NAME_MAPPING: Dict[str, str] = {
    "memory_service": "Memory Service",
    "config_service": "Configuration Service",
    "telemetry_service": "Telemetry Service",
    "audit_service": "Audit Service",
    "incident_service": "Incident Management Service",
    "tsdb_consolidation_service": "Time-Series Database Consolidation Service",
    "authentication_service": "Authentication Service",
    "resource_monitor": "Resource Monitor",
    "database_maintenance": "Database Maintenance",
    "secrets_service": "Secrets Service",
    "initialization_service": "Initialization Service",
    "shutdown_service": "Shutdown Service",
    "time_service": "Time Service",
    "task_scheduler": "Task Scheduler",
    "wise_authority": "Wise Authority",
    "adaptive_filter": "Adaptive Filter",
    "visibility_service": "Visibility Service",
    "consent_service": "Consent Service",
    "self_observation": "Self-Observation Service",
    "llm_service": "LLM Service",
    "runtime_control": "Runtime Control",
    "secrets_tool": "Secrets Tool",
}


def generate_semantic_service_name(service_name: str) -> str:
    """
    Generate human-readable semantic name for a service.

    Uses a lookup table approach for better maintainability and lower complexity.

    Args:
        service_name: Technical service name

    Returns:
        Human-readable service name
    """
    # Direct lookup in mapping table
    if service_name in SERVICE_NAME_MAPPING:
        return SERVICE_NAME_MAPPING[service_name]

    # Fallback: Convert snake_case to Title Case
    return service_name.replace("_", " ").title()


def get_service_category(service_name: str) -> str:
    """
    Categorize service by type.

    Args:
        service_name: Service name

    Returns:
        Service category
    """
    graph_services = {"memory", "config", "telemetry", "audit", "incident", "tsdb"}
    infrastructure = {"authentication", "resource", "database", "secrets"}
    lifecycle = {"initialization", "shutdown", "time", "task"}
    governance = {"wise", "adaptive", "visibility", "consent", "observation"}

    name_lower = service_name.lower()

    if any(svc in name_lower for svc in graph_services):
        return "graph"
    elif any(svc in name_lower for svc in infrastructure):
        return "infrastructure"
    elif any(svc in name_lower for svc in lifecycle):
        return "lifecycle"
    elif any(svc in name_lower for svc in governance):
        return "governance"
    else:
        return "runtime"


# ============================================================================
# CONTINUITY SUMMARY HELPERS
# ============================================================================


def _extract_timestamp_from_node_id(node: Any, prefix: str) -> Optional[datetime]:
    """Extract timestamp from lifecycle node ID.

    Args:
        node: Graph node with lifecycle event
        prefix: Node ID prefix ('startup_' or 'shutdown_')

    Returns:
        Datetime if successfully extracted, None otherwise
    """
    if not hasattr(node, "id") or not node.id.startswith(prefix):
        return None

    ts_str = node.id.replace(prefix, "")
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def _extract_shutdown_reason_from_node(node: Any) -> Optional[str]:
    """Extract shutdown reason from shutdown node attributes.

    Args:
        node: Shutdown graph node

    Returns:
        Shutdown reason string if found, None otherwise
    """
    if not hasattr(node, "attributes"):
        return None

    attrs = node.attributes

    # Handle both dict (NodeAttributes) and object (GraphNodeAttributes) forms
    if isinstance(attrs, dict):
        reason = attrs.get("reason")
        return str(reason) if reason is not None else None
    elif hasattr(attrs, "reason"):
        reason = attrs.reason
        return str(reason) if reason is not None else None

    return None


def _extract_shutdown_consent_from_node(node: Any) -> Optional[str]:
    """Extract shutdown consent status from shutdown node attributes.

    Args:
        node: Shutdown graph node

    Returns:
        Consent status string ('accepted', 'rejected', or 'manual') if found, None otherwise
    """
    if not hasattr(node, "attributes"):
        return None

    attrs = node.attributes

    # Handle both dict (NodeAttributes) and object (GraphNodeAttributes) forms
    if isinstance(attrs, dict):
        consent = attrs.get("consent_status")
        return str(consent) if consent is not None else None
    elif hasattr(attrs, "consent_status"):
        consent = attrs.consent_status
        return str(consent) if consent is not None else None

    return None


def _extract_timestamps_from_nodes(nodes: List[Any], prefix: str) -> List[datetime]:
    """Extract all valid timestamps from lifecycle nodes.

    Args:
        nodes: List of graph nodes
        prefix: Node ID prefix to match

    Returns:
        List of extracted timestamps
    """
    timestamps = []
    for node in nodes:
        ts = _extract_timestamp_from_node_id(node, prefix)
        if ts:
            timestamps.append(ts)
    return timestamps


def _merge_and_sort_events(
    startup_timestamps: List[datetime], shutdown_timestamps: List[datetime]
) -> List[Tuple[str, datetime]]:
    """Merge startup/shutdown timestamps into sorted event list.

    Args:
        startup_timestamps: List of startup times
        shutdown_timestamps: List of shutdown times

    Returns:
        Sorted list of (event_type, timestamp) tuples
    """
    all_events = []
    for ts in startup_timestamps:
        all_events.append(("startup", ts))
    for ts in shutdown_timestamps:
        all_events.append(("shutdown", ts))
    all_events.sort(key=lambda x: x[1])
    return all_events


def _infer_missing_startup(
    last_shutdown_ts: Optional[datetime], current_shutdown_ts: datetime
) -> Tuple[datetime, float]:
    """Infer startup time for shutdown without matching startup.

    Args:
        last_shutdown_ts: Previous shutdown timestamp (None if first shutdown)
        current_shutdown_ts: Current shutdown timestamp

    Returns:
        Tuple of (inferred_startup_time, offline_seconds_to_add)
    """
    from datetime import timedelta

    if last_shutdown_ts is None:
        # First shutdown: assume startup 1 minute BEFORE
        inferred_startup = current_shutdown_ts - timedelta(minutes=1)
        logger.debug(
            f"First shutdown at {current_shutdown_ts} without startup, "
            f"inferring startup 1 minute before at {inferred_startup}"
        )
        return inferred_startup, 0.0
    else:
        # Subsequent shutdown: assume startup 1 minute AFTER previous shutdown
        inferred_startup = last_shutdown_ts + timedelta(minutes=1)
        logger.debug(
            f"Shutdown at {current_shutdown_ts} without startup after previous shutdown at {last_shutdown_ts}, "
            f"inferring startup 1 minute after at {inferred_startup}"
        )
        return inferred_startup, 60.0  # 1 minute downtime


def _calculate_online_offline_durations(all_events: List[Tuple[str, datetime]]) -> Tuple[float, float]:
    """Calculate total online/offline durations from lifecycle events.

    Args:
        all_events: Sorted list of (event_type, timestamp) tuples

    Returns:
        Tuple of (total_online_seconds, total_offline_seconds)
    """
    total_online = 0.0
    total_offline = 0.0
    current_session_start = None
    last_shutdown = None

    for i, (event_type, ts) in enumerate(all_events):
        if event_type == "startup":
            current_session_start = ts

        elif event_type == "shutdown":
            # Infer missing startup if needed
            if not current_session_start:
                current_session_start, offline_to_add = _infer_missing_startup(last_shutdown, ts)
                total_offline += offline_to_add

            # Calculate session duration
            session_duration = (ts - current_session_start).total_seconds()
            total_online += session_duration

            # Calculate offline time to next startup
            if i + 1 < len(all_events) and all_events[i + 1][0] == "startup":
                next_startup = all_events[i + 1][1]
                offline_duration = (next_startup - ts).total_seconds()
                total_offline += offline_duration

            last_shutdown = ts
            current_session_start = None

    return total_online, total_offline


async def _fetch_lifecycle_nodes(memory_service: Any) -> Tuple[List[Any], List[Any]]:
    """Fetch startup and shutdown nodes from memory.

    Args:
        memory_service: Memory service for queries

    Returns:
        Tuple of (startup_nodes, shutdown_nodes)
    """
    from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
    from ciris_engine.schemas.services.graph_core import GraphScope

    startup_filter = MemorySearchFilter(scope=GraphScope.IDENTITY.value, node_type="agent", limit=1000)
    startup_nodes = await memory_service.search(query="startup", filters=startup_filter)

    shutdown_filter = MemorySearchFilter(scope=GraphScope.IDENTITY.value, node_type="agent", limit=1000)
    shutdown_nodes = await memory_service.search(query="shutdown", filters=shutdown_filter)

    return startup_nodes, shutdown_nodes


async def build_continuity_summary_from_memory(
    memory_service: Optional[Any], time_service: Any, start_time: Optional[datetime]
) -> Optional[ContinuitySummary]:
    """Build continuity summary from startup/shutdown memory nodes.

    Args:
        memory_service: Memory service to query for lifecycle events
        time_service: Time service for current time
        start_time: Service start time for current session

    Returns:
        ContinuitySummary if memory service available, None otherwise
    """
    if not memory_service:
        return None

    try:
        now = time_service.now() if time_service else datetime.now(timezone.utc)

        # Fetch lifecycle nodes
        startup_nodes, shutdown_nodes = await _fetch_lifecycle_nodes(memory_service)

        # Extract timestamps
        startup_timestamps = _extract_timestamps_from_nodes(startup_nodes, "startup_")
        shutdown_timestamps = _extract_timestamps_from_nodes(shutdown_nodes, "shutdown_")

        # Calculate basic metrics
        first_startup = min(startup_timestamps) if startup_timestamps else None
        last_shutdown_ts = max(shutdown_timestamps) if shutdown_timestamps else None

        # Extract last shutdown reason and consent status from the most recent shutdown node
        last_shutdown_reason = None
        last_shutdown_consent = None
        if shutdown_nodes and last_shutdown_ts:
            # Find the shutdown node with the matching timestamp
            for node in shutdown_nodes:
                node_ts = _extract_timestamp_from_node_id(node, "shutdown_")
                if node_ts == last_shutdown_ts:
                    last_shutdown_reason = _extract_shutdown_reason_from_node(node)
                    last_shutdown_consent = _extract_shutdown_consent_from_node(node)
                    break

        # Merge and calculate durations
        all_events = _merge_and_sort_events(startup_timestamps, shutdown_timestamps)
        total_online, total_offline = _calculate_online_offline_durations(all_events)

        # Add current session if online
        current_session_duration = 0.0
        if start_time:
            current_session_duration = (now - start_time).total_seconds()
            total_online += current_session_duration

        # Calculate averages
        total_shutdowns = len(shutdown_timestamps)
        avg_online = total_online / (total_shutdowns + 1) if total_shutdowns >= 0 else 0.0
        avg_offline = total_offline / total_shutdowns if total_shutdowns > 0 else 0.0

        return ContinuitySummary(
            first_startup=first_startup,
            total_time_online_seconds=total_online,
            total_time_offline_seconds=total_offline,
            total_shutdowns=total_shutdowns,
            average_time_online_seconds=avg_online,
            average_time_offline_seconds=avg_offline,
            current_session_start=start_time,
            current_session_duration_seconds=current_session_duration,
            last_shutdown=last_shutdown_ts,
            last_shutdown_reason=last_shutdown_reason,
            last_shutdown_consent=last_shutdown_consent,
        )

    except Exception as e:
        logger.warning(f"Failed to build continuity summary: {e}")
        return None
