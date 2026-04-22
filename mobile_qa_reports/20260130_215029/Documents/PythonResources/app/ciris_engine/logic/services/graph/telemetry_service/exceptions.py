"""
Telemetry service exceptions.

Fail fast and loud - no fallback values or fake data.
All exceptions provide clear context about what failed.
"""


class TelemetryServiceError(Exception):
    """Base exception for telemetry service errors."""

    pass


class MetricCollectionError(TelemetryServiceError):
    """Raised when metric collection fails.

    This indicates a problem querying or processing metrics from persistence.
    """

    pass


class InvalidMetricDataError(TelemetryServiceError):
    """Raised when metric data is invalid or cannot be parsed.

    This indicates the data returned from persistence doesn't match expected schema.
    """

    pass


class InvalidTimestampError(TelemetryServiceError):
    """Raised when metric timestamp is invalid.

    This means the timestamp field is missing, wrong type, or unparseable.
    """

    pass


class UnknownMetricTypeError(TelemetryServiceError):
    """Raised when metric type is not recognized.

    This indicates a programming error - metric type should be from known set.
    """

    pass


class MemoryBusUnavailableError(TelemetryServiceError):
    """Raised when memory bus is not available for queries.

    This means telemetry service started before memory bus was initialized,
    or memory bus was shut down. Caller should handle gracefully.
    """

    pass


class ThoughtDepthQueryError(TelemetryServiceError):
    """Raised when thought depth database query fails.

    This indicates a problem with database access or SQL execution.
    """

    pass


class NoThoughtDataError(TelemetryServiceError):
    """Raised when no thought data exists in the requested time window.

    This is NOT an error condition during startup or low-activity periods.
    Caller should handle appropriately (e.g., skip thought depth metric).
    """

    pass


class RuntimeControlBusUnavailableError(TelemetryServiceError):
    """Raised when runtime control bus is not available.

    This means runtime control service hasn't been registered yet or was shut down.
    """

    pass


class QueueStatusUnavailableError(TelemetryServiceError):
    """Raised when queue status cannot be retrieved from runtime control.

    This indicates runtime control service exists but get_processor_queue_status failed.
    """

    pass


class ServiceStartTimeUnavailableError(TelemetryServiceError):
    """Raised when service start_time is not set.

    This is a programming error - start_time should be set during service initialization.
    """

    pass
