import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest, MetricsQuery
from ciris_engine.schemas.persistence.correlations import ChannelInfo
from ciris_engine.schemas.telemetry.core import CorrelationType, ServiceCorrelation, ServiceCorrelationStatus
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService

logger = logging.getLogger(__name__)

# JSON path constants for database queries
JSON_PATH_CHANNEL_ID = "$.channel_id"


def _parse_response_data(
    response_data_json: Optional[JSONDict], timestamp: Optional[datetime] = None
) -> Optional[JSONDict]:
    """Parse response data JSON with backward compatibility for missing fields."""
    if not response_data_json:
        return None

    # Ensure response_timestamp exists for backward compatibility
    if isinstance(response_data_json, dict) and "response_timestamp" not in response_data_json:
        # Use the correlation timestamp or current time as fallback
        response_data_json["response_timestamp"] = (timestamp or datetime.now(timezone.utc)).isoformat()

    # Note: We keep returning Dict for backward compatibility with database storage
    # The typed schemas are used at the API boundaries
    return response_data_json


def add_correlation(
    corr: ServiceCorrelation, time_service: Optional[TimeServiceProtocol] = None, db_path: Optional[str] = None
) -> str:
    sql = """
        INSERT INTO service_correlations (
            correlation_id, service_type, handler_name, action_type,
            request_data, response_data, status, created_at, updated_at,
            correlation_type, timestamp, metric_name, metric_value, log_level,
            trace_id, span_id, parent_span_id, tags, retention_policy
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # Convert timestamp to ISO string
    timestamp_str = corr.timestamp.isoformat()

    params = (
        corr.correlation_id,
        corr.service_type,
        corr.handler_name,
        corr.action_type,
        (
            corr.request_data.model_dump_json()
            if corr.request_data and hasattr(corr.request_data, "model_dump_json")
            else json.dumps(corr.request_data) if corr.request_data else None
        ),
        (
            corr.response_data.model_dump_json()
            if corr.response_data and hasattr(corr.response_data, "model_dump_json")
            else json.dumps(corr.response_data) if corr.response_data else None
        ),
        corr.status.value,
        (
            corr.created_at.isoformat()
            if isinstance(corr.created_at, datetime)
            else (
                str(corr.created_at)
                if corr.created_at
                else (time_service.now().isoformat() if time_service else datetime.now(timezone.utc).isoformat())
            )
        ),
        (
            corr.updated_at.isoformat()
            if isinstance(corr.updated_at, datetime)
            else (
                str(corr.updated_at)
                if corr.updated_at
                else (time_service.now().isoformat() if time_service else datetime.now(timezone.utc).isoformat())
            )
        ),
        corr.correlation_type.value,
        timestamp_str,
        corr.metric_data.metric_name if corr.metric_data else None,
        corr.metric_data.metric_value if corr.metric_data else None,
        corr.log_data.log_level if corr.log_data else None,
        corr.trace_context.trace_id if corr.trace_context else None,
        corr.trace_context.span_id if corr.trace_context else None,
        corr.trace_context.parent_span_id if corr.trace_context else None,
        json.dumps(corr.tags) if corr.tags else None,
        corr.retention_policy,
    )
    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.debug("Inserted correlation %s", corr.correlation_id)
        return corr.correlation_id
    except Exception as e:
        logger.exception("Failed to add correlation %s: %s", corr.correlation_id, e)
        raise


def update_correlation(
    update_request_or_id: Union[CorrelationUpdateRequest, str],
    correlation_or_time_service: Union[ServiceCorrelation, TimeServiceProtocol],
    time_service: Optional[TimeServiceProtocol] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update correlation - handles both old and new signatures for compatibility."""
    # Handle old signature: update_correlation(correlation_id, correlation, time_service)
    if isinstance(update_request_or_id, str) and isinstance(correlation_or_time_service, ServiceCorrelation):
        # Convert old signature to new
        correlation = correlation_or_time_service
        actual_time_service = time_service
        if not actual_time_service:
            raise ValueError("time_service required for old signature")

        # Build update request from correlation object
        update_request = CorrelationUpdateRequest(
            correlation_id=update_request_or_id,
            response_data=(
                {
                    "success": str(getattr(correlation.response_data, "success", False)).lower(),
                    "error_message": str(getattr(correlation.response_data, "error_message", "")),
                    "execution_time_ms": str(getattr(correlation.response_data, "execution_time_ms", 0)),
                    "response_timestamp": str(
                        getattr(correlation.response_data, "response_timestamp", actual_time_service.now()).isoformat()
                    ),
                }
                if correlation.response_data
                else None
            ),
            status=(
                ServiceCorrelationStatus.COMPLETED
                if correlation.response_data and getattr(correlation.response_data, "success", False)
                else ServiceCorrelationStatus.FAILED
            ),
        )
        # db_path is already set from parameter
    # Handle new signature: update_correlation(update_request, time_service)
    elif isinstance(update_request_or_id, CorrelationUpdateRequest):
        update_request = update_request_or_id
        actual_time_service = correlation_or_time_service  # type: ignore[assignment]
        if not hasattr(actual_time_service, "now"):
            raise ValueError("time_service must have 'now' method for new signature")
    else:
        raise ValueError("Invalid arguments to update_correlation")

    # Call the implementation
    return _update_correlation_impl(update_request, actual_time_service, db_path)  # type: ignore[arg-type]


def _update_correlation_impl(
    update_request: CorrelationUpdateRequest, time_service: TimeServiceProtocol, db_path: Optional[str] = None
) -> bool:
    updates: List[Any] = []
    params: List[Any] = []
    if update_request.response_data is not None:
        updates.append("response_data = ?")
        params.append(json.dumps(update_request.response_data))
    if update_request.status is not None:
        updates.append("status = ?")
        params.append(update_request.status.value)
    if update_request.metric_value is not None:
        updates.append("metric_value = ?")
        params.append(update_request.metric_value)
    if update_request.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(update_request.tags))
    updates.append("updated_at = ?")
    params.append(time_service.now().isoformat())
    params.append(update_request.correlation_id)

    sql = f"UPDATE service_correlations SET {', '.join(updates)} WHERE correlation_id = ?"  # nosec B608 - updates are hardcoded strings like 'status = ?'
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.exception("Failed to update correlation %s: %s", update_request.correlation_id, e)
        return False


def get_correlation(correlation_id: str, db_path: Optional[str] = None) -> Optional[ServiceCorrelation]:
    sql = "SELECT * FROM service_correlations WHERE correlation_id = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (correlation_id,))
            row = cursor.fetchone()
            return _row_to_service_correlation(row) if row else None
    except Exception as e:
        logger.exception("Failed to fetch correlation %s: %s", correlation_id, e)
        return None


def get_correlations_by_task_and_action(
    task_id: str, action_type: str, status: Optional[ServiceCorrelationStatus] = None, db_path: Optional[str] = None
) -> List[ServiceCorrelation]:
    """Get correlations for a specific task and action type."""
    adapter = get_adapter()
    sql = f"""
        SELECT * FROM service_correlations
        WHERE action_type = {adapter.placeholder()}
        AND {adapter.json_extract('request_data', '$.task_id')} = {adapter.placeholder()}
    """
    params = [action_type, task_id]

    if status is not None:
        sql += f" AND status = {adapter.placeholder()}"
        params.append(status.value)

    sql += " ORDER BY created_at DESC"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            return [_row_to_service_correlation(row) for row in rows]
    except Exception as e:
        logger.exception("Failed to fetch correlations for task %s and action %s: %s", task_id, action_type, e)
        return []


def get_correlations_by_type_and_time(
    correlation_type: CorrelationType,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    metric_names: Optional[List[str]] = None,
    log_levels: Optional[List[str]] = None,
    limit: int = 1000,
    db_path: Optional[str] = None,
) -> List[ServiceCorrelation]:
    """Get correlations by type with optional time filtering for TSDB queries."""
    sql = "SELECT * FROM service_correlations WHERE correlation_type = ?"
    if hasattr(correlation_type, "value"):
        params: List[Any] = [correlation_type.value]
    else:
        params = [str(correlation_type)]

    if start_time:
        sql += " AND timestamp >= ?"
        params.append(start_time)

    if end_time:
        sql += " AND timestamp <= ?"
        params.append(end_time)

    if metric_names:
        placeholders = ",".join("?" * len(metric_names))
        sql += f" AND metric_name IN ({placeholders})"  # nosec B608 - placeholders are '?' strings, not user input
        params.extend(metric_names)

    if log_levels:
        placeholders = ",".join("?" * len(log_levels))
        sql += f" AND log_level IN ({placeholders})"  # nosec B608 - placeholders are '?' strings, not user input
        params.extend(log_levels)

    sql += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            return [_row_to_service_correlation(row) for row in rows]
    except Exception as e:
        logger.exception("Failed to fetch correlations by type %s: %s", correlation_type, e)
        return []


def get_correlations_by_channel(
    channel_id: str, limit: int = 50, before: Optional[datetime] = None, db_path: Optional[str] = None
) -> List[ServiceCorrelation]:
    """Get correlations for a specific channel (for message history)."""
    adapter = get_adapter()
    ph = adapter.placeholder()
    json_channel_id = adapter.json_extract("request_data", JSON_PATH_CHANNEL_ID)

    sql = f"""
        SELECT * FROM service_correlations
        WHERE (
            (action_type = 'speak' AND {json_channel_id} = {ph}) OR
            (action_type = 'observe' AND {json_channel_id} = {ph})
        )
    """
    params: List[Any] = [channel_id, channel_id]

    if before:
        sql += f" AND timestamp < {ph}"
        before_str = before.isoformat() if hasattr(before, "isoformat") else str(before)
        params.append(before_str)

    sql += f" ORDER BY timestamp DESC LIMIT {ph}"
    params.append(limit)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            correlations = [_row_to_service_correlation(row) for row in rows]
            # Reverse to get chronological order (oldest first)
            correlations.reverse()
            return correlations
    except Exception as e:
        logger.exception("Failed to fetch correlations for channel %s: %s", channel_id, e)
        return []


def get_metrics_timeseries(query: MetricsQuery, db_path: Optional[str] = None) -> List[ServiceCorrelation]:
    """Get metric correlations as time series data."""
    adapter = get_adapter()
    ph = adapter.placeholder()

    sql = f"""
        SELECT * FROM service_correlations
        WHERE correlation_type = 'metric_datapoint'
        AND metric_name = {ph}
    """
    params: List[Any] = [query.metric_name]

    if query.start_time:
        sql += f" AND timestamp >= {ph}"
        params.append(query.start_time.isoformat() if hasattr(query.start_time, "isoformat") else query.start_time)

    if query.end_time:
        sql += f" AND timestamp <= {ph}"
        params.append(query.end_time.isoformat() if hasattr(query.end_time, "isoformat") else query.end_time)

    if query.tags:
        for key, value in query.tags.items():
            sql += f" AND {adapter.json_extract('tags', f'$.{key}')} = {ph}"
            params.append(value)

    # Default limit to 1000 if not specified
    limit = 1000 if not hasattr(query, "limit") else getattr(query, "limit", 1000)
    sql += f" ORDER BY timestamp ASC LIMIT {ph}"
    params.append(limit)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()

            correlations = []
            for row in rows:
                timestamp = None
                if row["timestamp"]:
                    try:
                        # Handle both 'Z' and '+00:00' formats
                        timestamp_str = row["timestamp"]
                        if timestamp_str.endswith("Z"):
                            timestamp_str = timestamp_str[:-1] + UTC_TIMEZONE_SUFFIX
                        timestamp = datetime.fromisoformat(timestamp_str)
                    except (ValueError, AttributeError):
                        timestamp = None

                # Import required types
                from ciris_engine.schemas.telemetry.core import LogData, MetricData, TraceContext

                # Build metric_data if this is a metric correlation
                metric_data = None
                if row["metric_name"] and row["metric_value"] is not None:
                    metric_data = MetricData(
                        metric_name=row["metric_name"],
                        metric_value=row["metric_value"],
                        metric_unit="count",
                        metric_type="gauge",
                        labels={},
                    )

                # Build log_data if this is a log correlation
                log_data = None
                if row["log_level"]:
                    log_data = LogData(
                        log_level=row["log_level"],
                        log_message="",  # Not stored in DB
                        logger_name="",
                        module_name="",
                        function_name="",
                        line_number=0,
                    )

                # Build trace_context if this is a trace correlation
                trace_context = None
                if row["trace_id"]:
                    trace_context = TraceContext(trace_id=row["trace_id"], span_id=row["span_id"] or "", span_name="")
                    if row["parent_span_id"]:
                        trace_context.parent_span_id = row["parent_span_id"]

                # Map 'success' to 'completed' for backwards compatibility
                status_value = row["status"]
                if status_value == "success":
                    status_value = "completed"

                correlations.append(
                    ServiceCorrelation(
                        correlation_id=row["correlation_id"],
                        service_type=row["service_type"],
                        handler_name=row["handler_name"],
                        action_type=row["action_type"],
                        request_data=json.loads(row["request_data"]) if row["request_data"] else None,
                        response_data=_parse_response_data(
                            json.loads(row["response_data"]) if row["response_data"] else None, timestamp
                        ),
                        status=ServiceCorrelationStatus(status_value),
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        correlation_type=CorrelationType(row["correlation_type"] or "service_interaction"),
                        timestamp=timestamp,
                        metric_data=metric_data,
                        log_data=log_data,
                        trace_context=trace_context,
                        tags={k: str(v) for k, v in json.loads(row["tags"]).items()} if row["tags"] else {},
                        retention_policy=row["retention_policy"] or "raw",
                    )
                )
            return correlations
    except Exception as e:
        logger.exception("Failed to fetch metrics timeseries for %s: %s", query.metric_name, e)
        return []


def get_active_channels_by_adapter(
    adapter_type: str,
    since_days: int = 30,
    time_service: Optional[TimeServiceProtocol] = None,
    db_path: Optional[str] = None,
) -> List[ChannelInfo]:
    """
    Get active channels for a specific adapter type from correlations.

    This function discovers channels organically from actual usage in both:
    - Recent correlations (last since_days)
    - Historical conversation summaries from TSDB consolidation

    Args:
        adapter_type: The adapter type (e.g., "discord", "api", "cli")
        since_days: Number of days to look back (default 30)
        time_service: Optional time service for testing
        db_path: Optional database path

    Returns:
        List of ChannelInfo objects with channel details
    """
    # Calculate cutoff time
    if time_service:
        cutoff_time = time_service.now() - timedelta(days=since_days)
    else:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=since_days)

    channels: Dict[str, ChannelInfo] = {}

    # Query recent correlations for speak/observe actions
    adapter = get_adapter()
    ph = adapter.placeholder()
    json_channel_id = adapter.json_extract("request_data", JSON_PATH_CHANNEL_ID)

    sql = f"""
        SELECT
            {json_channel_id} as channel_id,
            MAX(timestamp) as last_activity,
            COUNT(*) as message_count
        FROM service_correlations
        WHERE action_type IN ('speak', 'observe')
        AND timestamp >= {ph}
        AND {json_channel_id} IS NOT NULL
        AND {json_channel_id} LIKE {ph}
        GROUP BY channel_id
    """

    # Build adapter pattern (e.g., "api_%" for API channels)
    adapter_pattern = f"{adapter_type}_%"

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (cutoff_time.isoformat(), adapter_pattern))
            rows = cursor.fetchall()

            for row in rows:
                channel_id = row[0]
                if channel_id:
                    # Parse timestamp
                    last_activity = None
                    if row[1]:
                        try:
                            timestamp_str = row[1]
                            if timestamp_str.endswith("Z"):
                                timestamp_str = timestamp_str[:-1] + UTC_TIMEZONE_SUFFIX
                            last_activity = datetime.fromisoformat(timestamp_str)
                        except (ValueError, AttributeError):
                            last_activity = cutoff_time

                    channels[channel_id] = ChannelInfo(
                        channel_id=channel_id,
                        channel_type=adapter_type,
                        last_activity=last_activity or cutoff_time,
                        message_count=row[2] or 0,
                        is_active=True,
                    )
    except Exception as e:
        logger.warning("Failed to query recent correlations: %s", e)

    # Also check conversation summaries from TSDB consolidation
    # These provide historical channel activity beyond the correlation retention window
    try:
        # Query memory graph for ConversationSummaryNodes
        json_period_start = adapter.json_extract("node_data", "$.period_start")
        sql_summaries = f"""
            SELECT
                node_data
            FROM graph_nodes
            WHERE node_type = 'ConversationSummaryNode'
            AND {json_period_start} >= {ph}
            ORDER BY {json_period_start} DESC
        """

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_summaries, (cutoff_time.isoformat(),))
            rows = cursor.fetchall()

            for row in rows:
                if row[0]:
                    try:
                        node_data = json.loads(row[0])
                        conversations_by_channel = node_data.get("conversations_by_channel", {})

                        # Extract channels matching our adapter type
                        for channel_id, conversations in conversations_by_channel.items():
                            if channel_id.startswith(f"{adapter_type}_"):
                                # Update channel info if not already present or if this is more recent
                                if channel_id not in channels:
                                    channels[channel_id] = ChannelInfo(
                                        channel_id=channel_id,
                                        channel_type=adapter_type,
                                        last_activity=datetime.fromisoformat(
                                            node_data.get("period_end", cutoff_time.isoformat())
                                        ),
                                        message_count=len(conversations),
                                        is_active=True,
                                    )
                                else:
                                    # Update message count
                                    channels[channel_id].message_count += len(conversations)
                    except Exception as e:
                        logger.debug("Failed to parse conversation summary: %s", e)
    except Exception as e:
        logger.debug("Memory graph query failed (expected if not using memory service): %s", e)

    # Convert to list and sort by last activity
    channel_list = list(channels.values())
    channel_list.sort(key=lambda x: x.last_activity, reverse=True)

    return channel_list


def get_channel_last_activity(
    channel_id: str, time_service: Optional[TimeServiceProtocol] = None, db_path: Optional[str] = None
) -> Optional[datetime]:
    """
    Get the last activity timestamp for a specific channel.

    Checks both recent correlations and TSDB conversation summaries.

    Args:
        channel_id: The channel ID to check
        time_service: Optional time service
        db_path: Optional database path

    Returns:
        Last activity datetime or None if no activity found
    """
    last_activity = None

    # Check recent correlations
    adapter = get_adapter()
    ph = adapter.placeholder()
    json_channel_id = adapter.json_extract("request_data", JSON_PATH_CHANNEL_ID)

    sql = f"""
        SELECT MAX(timestamp) as last_activity
        FROM service_correlations
        WHERE action_type IN ('speak', 'observe')
        AND {json_channel_id} = {ph}
    """

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()

            if row and row[0]:
                try:
                    timestamp_str = row[0]
                    if timestamp_str.endswith("Z"):
                        timestamp_str = timestamp_str[:-1] + UTC_TIMEZONE_SUFFIX
                    last_activity = datetime.fromisoformat(timestamp_str)
                except (ValueError, AttributeError):
                    pass
    except Exception as e:
        logger.warning("Failed to query channel activity: %s", e)

    # Also check conversation summaries for historical activity
    try:
        json_period_end = adapter.json_extract("node_data", "$.period_end")
        json_conversations = adapter.json_extract("node_data", "$.conversations_by_channel")

        sql_summaries = f"""
            SELECT
                {json_period_end} as period_end
            FROM graph_nodes
            WHERE node_type = 'ConversationSummaryNode'
            AND {json_conversations} LIKE {ph}
            ORDER BY {json_period_end} DESC
            LIMIT 1
        """

        # Use LIKE pattern to find channels in the JSON
        pattern = f'%"{channel_id}":%'

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_summaries, (pattern,))
            row = cursor.fetchone()

            if row and row[0]:
                try:
                    summary_time = datetime.fromisoformat(row[0])
                    if not last_activity or summary_time > last_activity:
                        last_activity = summary_time
                except (ValueError, AttributeError):
                    pass
    except Exception as e:
        logger.debug("Memory graph query failed: %s", e)

    return last_activity


def _row_to_service_correlation(row: Any) -> ServiceCorrelation:
    """
    Convert a database row to a ServiceCorrelation object.

    Centralizes the row parsing logic to eliminate code duplication.

    Args:
        row: Database row with correlation data

    Returns:
        ServiceCorrelation object
    """
    # Parse timestamp if present - handle both PostgreSQL (datetime) and SQLite (string)
    timestamp = None
    if row["timestamp"]:
        try:
            timestamp_value = row["timestamp"]
            # PostgreSQL returns datetime objects directly
            if isinstance(timestamp_value, datetime):
                timestamp = timestamp_value
            # SQLite returns strings - parse them
            elif isinstance(timestamp_value, str):
                # Handle both 'Z' and '+00:00' formats
                if timestamp_value.endswith("Z"):
                    timestamp_value = timestamp_value[:-1] + UTC_TIMEZONE_SUFFIX
                timestamp = datetime.fromisoformat(timestamp_value)
        except (ValueError, AttributeError, TypeError):
            timestamp = None

    # Parse request_data - handle PostgreSQL JSONB vs SQLite TEXT
    request_data_raw = row["request_data"]
    if request_data_raw:
        request_data_json = request_data_raw if isinstance(request_data_raw, dict) else json.loads(request_data_raw)
    else:
        request_data_json = {}

    # Parse response_data - handle PostgreSQL JSONB vs SQLite TEXT
    response_data_raw = row["response_data"]
    if response_data_raw:
        response_data_parsed = (
            response_data_raw if isinstance(response_data_raw, dict) else json.loads(response_data_raw)
        )
    else:
        response_data_parsed = None

    # Parse tags - handle PostgreSQL JSONB vs SQLite TEXT
    tags_raw = row["tags"]
    if tags_raw:
        tags_parsed = tags_raw if isinstance(tags_raw, dict) else json.loads(tags_raw)
    else:
        tags_parsed = {}

    # Map 'success' to 'completed' for backwards compatibility
    status_value = row["status"]
    if status_value == "success":
        status_value = "completed"

    # Build the correlation without None values for optional fields
    correlation_data = {
        "correlation_id": row["correlation_id"],
        "service_type": row["service_type"],
        "handler_name": row["handler_name"],
        "action_type": row["action_type"],
        "request_data": request_data_json if request_data_json else None,
        "response_data": _parse_response_data(response_data_parsed, timestamp),
        "status": ServiceCorrelationStatus(status_value),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "correlation_type": CorrelationType(row["correlation_type"] or "service_interaction"),
        "timestamp": timestamp or datetime.now(timezone.utc),
        "tags": tags_parsed,
        "retention_policy": row["retention_policy"] or "raw",
    }

    # Only add optional TSDB fields if they have values
    if row["metric_name"] and row["metric_value"] is not None:
        from ciris_engine.schemas.telemetry.core import MetricData

        correlation_data["metric_data"] = MetricData(
            metric_name=row["metric_name"],
            metric_value=row["metric_value"],
            metric_unit="count",
            metric_type="gauge",
            labels={},
        )

    if row["log_level"]:
        from ciris_engine.schemas.telemetry.core import LogData

        correlation_data["log_data"] = LogData(
            log_level=row["log_level"],
            log_message="",
            logger_name="",
            module_name="",
            function_name="",
            line_number=0,
        )

    if row["trace_id"]:
        from ciris_engine.schemas.telemetry.core import TraceContext

        trace_context = TraceContext(trace_id=row["trace_id"], span_id=row["span_id"] or "", span_name="")
        if row["parent_span_id"]:
            trace_context.parent_span_id = row["parent_span_id"]
        correlation_data["trace_context"] = trace_context

    return ServiceCorrelation(**correlation_data)


def is_admin_channel(channel_id: str, db_path: Optional[str] = None) -> bool:
    """
    Determine if a channel belongs to an admin user.

    For API channels, checks if the channel has been used with admin credentials.
    This is done by looking for correlations with admin role in the tags.

    Args:
        channel_id: The channel ID to check
        db_path: Optional database path

    Returns:
        True if the channel is associated with admin usage
    """
    # Only API channels can be admin channels
    if not channel_id.startswith("api_"):
        return False

    # Check for admin role in correlation tags
    adapter = get_adapter()
    ph = adapter.placeholder()
    json_channel_id = adapter.json_extract("request_data", JSON_PATH_CHANNEL_ID)
    json_user_role = adapter.json_extract("tags", "$.user_role")
    json_is_admin = adapter.json_extract("tags", "$.is_admin")
    json_auth_role = adapter.json_extract("tags", "$.auth.role")

    sql = f"""
        SELECT COUNT(*) as admin_count
        FROM service_correlations
        WHERE {json_channel_id} = {ph}
        AND (
            {json_user_role} IN ('ADMIN', 'AUTHORITY', 'SYSTEM_ADMIN')
            OR {json_is_admin} = 1
            OR {json_auth_role} IN ('ADMIN', 'AUTHORITY', 'SYSTEM_ADMIN')
        )
        LIMIT 1
    """

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (channel_id,))
            row = cursor.fetchone()

            if row and row[0] > 0:
                return True
    except Exception as e:
        logger.warning("Failed to check admin status for channel %s: %s", channel_id, e)

    return False


def get_recent_correlations(limit: int = 100, db_path: Optional[str] = None) -> List[ServiceCorrelation]:
    """
    Get recent correlations ordered by timestamp.

    Args:
        limit: Maximum number of correlations to return (default 100)
        db_path: Optional database path

    Returns:
        List of recent ServiceCorrelation objects
    """
    sql = """
        SELECT * FROM service_correlations
        ORDER BY timestamp DESC
        LIMIT ?
    """

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()

            return [_row_to_service_correlation(row) for row in rows]
    except Exception as e:
        logger.exception("Failed to fetch recent correlations: %s", e)
        return []


async def add_correlation_with_telemetry(
    corr: ServiceCorrelation,
    time_service: Optional[TimeServiceProtocol] = None,
    telemetry_service: Optional["GraphTelemetryService"] = None,
    db_path: Optional[str] = None,
) -> str:
    """
    Add correlation to both persistence (SQLite) and telemetry service (memory graph).

    This ensures distributed tracing works by storing correlations in the memory graph
    for OTLP export while also persisting them to SQLite for durability.

    Args:
        corr: The ServiceCorrelation to store
        time_service: Optional time service for timestamps
        telemetry_service: Optional telemetry service for distributed tracing
        db_path: Optional database path for SQLite storage

    Returns:
        The correlation ID
    """
    # Store in SQLite persistence
    correlation_id = add_correlation(corr, time_service, db_path)

    # Also store in telemetry service for distributed tracing if available
    if telemetry_service and hasattr(telemetry_service, "_store_correlation"):
        try:
            await telemetry_service._store_correlation(corr)
            logger.debug(f"Stored correlation {correlation_id} in telemetry service for tracing")
        except Exception as e:
            # Don't fail if telemetry storage fails - it's supplementary
            logger.warning(f"Failed to store correlation in telemetry service: {e}")

    return correlation_id
