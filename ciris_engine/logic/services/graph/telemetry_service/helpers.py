"""
Helper functions for telemetry service refactoring.

These break down the complex get_telemetry_summary method into focused,
testable components. All functions fail fast and loud - no fallback data.
"""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, Union

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
from ciris_engine.schemas.runtime.system_context import TelemetrySummary
from ciris_engine.schemas.services.graph.telemetry import MetricAggregates, MetricRecord

if TYPE_CHECKING:
    from ciris_engine.logic.buses.memory_bus import MemoryBus
    from ciris_engine.logic.buses.runtime_control_bus import RuntimeControlBus
    from ciris_engine.logic.services.graph.telemetry_service.service import GraphTelemetryService

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

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            # Use window_start parameter for consistent timing with other telemetry calculations
            cursor.execute(
                """
                SELECT AVG(thought_depth) as avg_depth
                FROM thoughts
                WHERE created_at >= ?
            """,
                (window_start.isoformat(),),
            )
            result = cursor.fetchone()
            if result and result[0] is not None:
                return float(result[0])
            else:
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
    cache: Dict[str, Tuple[datetime, TelemetrySummary]],
    cache_key: str,
    now: datetime,
    ttl_seconds: int,
) -> Optional[TelemetrySummary]:
    """Check if cached telemetry summary is still valid.

    Args:
        cache: Summary cache dictionary
        cache_key: Key to look up in cache
        now: Current time
        ttl_seconds: Cache TTL in seconds

    Returns:
        Cached TelemetrySummary if valid, None otherwise
    """
    if cache_key in cache:
        cached_time, cached_summary = cache[cache_key]
        if (now - cached_time).total_seconds() < ttl_seconds:
            return cached_summary
    return None


def store_summary_cache(
    cache: Dict[str, Tuple[datetime, TelemetrySummary]],
    cache_key: str,
    now: datetime,
    summary: TelemetrySummary,
) -> None:
    """Store telemetry summary in cache.

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


def build_telemetry_summary(
    window_start: datetime,
    window_end: datetime,
    uptime_seconds: float,
    aggregates: MetricAggregates,
    error_rate: float,
    avg_thought_depth: float,
    queue_saturation: float,
    service_latency_ms: Dict[str, float],
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
    )

# =============================================================================
# QUERY_METRICS HELPERS (CC 22 → 6 reduction)
# =============================================================================


def calculate_query_time_window(
    start_time: Optional[datetime], end_time: Optional[datetime], now: datetime
) -> int:
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
        data: Timeseries data point with tags attribute
        tags: Optional dictionary of tags to match

    Returns:
        True if data matches all tags (or tags is None)
    """
    if not tags:
        return True

    data_tags = getattr(data, "tags", None) or {}
    return all(data_tags.get(k) == v for k, v in tags.items())


def filter_by_time_range(
    data: object, start_time: Optional[datetime], end_time: Optional[datetime]
) -> bool:
    """
    Check if timeseries data timestamp is within the specified range.

    Args:
        data: Timeseries data point with timestamp attribute
        start_time: Optional start of time range
        end_time: Optional end of time range

    Returns:
        True if timestamp is within range (or no range specified)
    """
    timestamp = getattr(data, "timestamp", None)
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
    timestamp = getattr(data, "timestamp", None)
    
    # Validate required fields
    if not (metric_name and value is not None and timestamp):
        return None

    return MetricRecord(
        metric_name=metric_name,
        value=value,
        timestamp=timestamp,
        tags=getattr(data, "tags", None) or {},
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


def generate_semantic_service_name(service_name: str, service_type: Optional[str] = None) -> str:
    """
    Generate human-readable semantic name for a service.

    Uses a lookup table approach for better maintainability and lower complexity.

    Args:
        service_name: Technical service name
        service_type: Optional service type hint (unused, kept for compatibility)

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
