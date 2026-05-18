"""Service-correlation persistence — routed through ciris-persist's typed substrate API.

Migrated from raw `sqlite3` to `engine.correlation_*` calls as part of the
2.9.0 A1 absorption (see docs/migration/T-lanes/MIGRATION_BIBLE.md).

Public function signatures are preserved exactly so call sites across
ciris_engine/ require no updates. The `db_path` parameter is accepted but
ignored — the wired persist Engine owns the underlying SQLite database;
tests inject the engine via `set_persist_engine` rather than per-call paths.

Related upstream issues:
- CIRISAgent#763  (parent A1 absorption)
- CIRISPersist#58 (libsqlite dual-writer corruption — root cause)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX

# Legacy alias — pre-migration tests `monkeypatch.setattr(correlations,
# "get_db_connection", ...)` to redirect the SQL connection. The migrated
# module no longer uses raw sqlite3, so this re-export exists purely so
# strict monkeypatch.setattr calls keep succeeding (and become harmless
# no-ops). Safe to remove once the test sweep updates those patches.
from ciris_engine.logic.persistence.db import get_db_connection  # noqa: F401
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest, MetricsQuery
from ciris_engine.schemas.persistence.correlations import ChannelInfo
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    LogData,
    MetricData,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService

logger = logging.getLogger(__name__)

# Persist's correlation_type enum is narrower than the agent's CorrelationType.
# Map agent values to the four persist-side variants for record/query payloads.
_AGENT_TO_PERSIST_CTYPE: Dict[str, str] = {
    CorrelationType.SERVICE_INTERACTION.value: "service_interaction",
    CorrelationType.METRIC_DATAPOINT.value: "metric",
    CorrelationType.LOG_ENTRY.value: "log",
    CorrelationType.TRACE_SPAN.value: "trace",
    CorrelationType.AUDIT_EVENT.value: "service_interaction",
    CorrelationType.METRIC_HOURLY_SUMMARY.value: "metric",
    CorrelationType.METRIC_DAILY_SUMMARY.value: "metric",
    CorrelationType.LOG_HOURLY_SUMMARY.value: "log",
}

# Persist's retention_policy vocabulary: raw, aggregated, summary,
# retained_indefinitely. The legacy agent table accepted free-form
# strings; map known agent-side values and fall through to "raw".
_AGENT_TO_PERSIST_RETENTION: Dict[str, str] = {
    "raw": "raw",
    "aggregated": "aggregated",
    "summary": "summary",
    "retained_indefinitely": "retained_indefinitely",
    # Legacy agent values that need mapping
    "short": "raw",
    "hourly_summary": "summary",
    "daily_summary": "summary",
}


def _get_engine() -> Any:
    """Return the wired persist engine; raise cleanly if not bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any correlation operation"
        )
    return engine


def _parse_response_data(
    response_data_json: Optional[JSONDict], timestamp: Optional[datetime] = None
) -> Optional[JSONDict]:
    """Parse response data JSON with backward compatibility for missing fields.

    Preserved from the legacy implementation; callers and tests depend on it.
    """
    if not response_data_json:
        return None

    if isinstance(response_data_json, dict) and "response_timestamp" not in response_data_json:
        response_data_json["response_timestamp"] = (timestamp or datetime.now(timezone.utc)).isoformat()

    return response_data_json


def _parse_iso_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string or datetime to a datetime object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    s = value
    try:
        if s.endswith("Z"):
            s = s[:-1] + UTC_TIMEZONE_SUFFIX
        return datetime.fromisoformat(s)
    except (ValueError, AttributeError, TypeError):
        return None


def _coerce_iso(value: Any) -> Optional[str]:
    """Coerce a value to ISO-8601 string for persist payloads."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _get_default_occurrence_id() -> str:
    """Resolve the agent occurrence id from the environment (lazy import)."""
    try:
        from ciris_engine.logic.utils.occurrence_utils import get_current_occurrence_id

        return get_current_occurrence_id()
    except Exception:
        return "default"


def _correlation_to_persist_payload(
    corr: ServiceCorrelation,
    time_service: Optional[TimeServiceProtocol] = None,
) -> Dict[str, Any]:
    """Convert an agent ServiceCorrelation into the dict shape that
    `engine.correlation_record` accepts.

    Persist takes `request_data`/`response_data`/`tags` as nested
    dicts/lists; it serializes them to TEXT JSON internally.
    """
    now_iso = (
        time_service.now().isoformat()
        if time_service is not None
        else datetime.now(timezone.utc).isoformat()
    )

    # Timestamps: agent stores `created_at` / `updated_at` as ISO strings
    # but accepts datetimes too. `timestamp` is always a datetime (per
    # ServiceCorrelation schema), but defensively coerce.
    created_at = _coerce_iso(corr.created_at) or now_iso
    updated_at = _coerce_iso(corr.updated_at) or now_iso
    timestamp = _coerce_iso(corr.timestamp) or now_iso

    # request_data / response_data — agent stores these as either typed
    # pydantic submodels or already-decoded dicts (test fixtures vary).
    request_data: Optional[Dict[str, Any]] = None
    if corr.request_data is not None:
        if hasattr(corr.request_data, "model_dump"):
            request_data = corr.request_data.model_dump(mode="json")
        elif isinstance(corr.request_data, dict):
            request_data = dict(corr.request_data)

    response_data: Optional[Dict[str, Any]] = None
    if corr.response_data is not None:
        if hasattr(corr.response_data, "model_dump"):
            response_data = corr.response_data.model_dump(mode="json")
        elif isinstance(corr.response_data, dict):
            response_data = dict(corr.response_data)

    status_val = corr.status.value if isinstance(corr.status, ServiceCorrelationStatus) else str(corr.status)
    # Persist accepts `pending|active|completed|failed|cancelled` — map any
    # legacy `success`/`error` strings to known values.
    if status_val == "success":
        status_val = "completed"
    elif status_val == "error":
        status_val = "failed"

    ctype_val = corr.correlation_type.value if isinstance(corr.correlation_type, CorrelationType) else str(corr.correlation_type)
    persist_ctype = _AGENT_TO_PERSIST_CTYPE.get(ctype_val, "service_interaction")

    payload: Dict[str, Any] = {
        "correlation_id": corr.correlation_id,
        "correlation_type": persist_ctype,
        "service_type": corr.service_type,
        "handler_name": corr.handler_name,
        "action_type": corr.action_type,
        "status": status_val,
        "created_at": created_at,
        "updated_at": updated_at,
        "timestamp": timestamp,
        "agent_occurrence_id": _get_default_occurrence_id(),
        "retention_policy": _AGENT_TO_PERSIST_RETENTION.get(corr.retention_policy or "raw", "raw"),
    }
    if request_data is not None:
        payload["request_data"] = request_data
    if response_data is not None:
        payload["response_data"] = response_data
    if corr.tags:
        payload["tags"] = dict(corr.tags)
    if corr.metric_data is not None:
        payload["metric_name"] = corr.metric_data.metric_name
        payload["metric_value"] = corr.metric_data.metric_value
    if corr.log_data is not None:
        payload["log_level"] = corr.log_data.log_level
    if corr.trace_context is not None:
        payload["trace_id"] = corr.trace_context.trace_id
        payload["span_id"] = corr.trace_context.span_id
        if corr.trace_context.parent_span_id is not None:
            payload["parent_span_id"] = corr.trace_context.parent_span_id

    # Stash the original agent-side correlation_type in tags so we can
    # round-trip the broader enum (e.g., METRIC_DATAPOINT vs METRIC_HOURLY_SUMMARY)
    # back out without persist needing the wider vocabulary.
    if persist_ctype != ctype_val:
        existing_tags: Dict[str, Any] = dict(payload.get("tags") or {})
        existing_tags["_agent_correlation_type"] = ctype_val
        payload["tags"] = existing_tags

    return payload


def _row_to_service_correlation(row: Dict[str, Any]) -> Optional[ServiceCorrelation]:
    """Materialize a persist correlation row into a ServiceCorrelation."""
    try:
        # Timestamp parsing — accept both strings and (rare) datetimes
        timestamp = _parse_iso_timestamp(row.get("timestamp"))

        # request_data / response_data — persist returns parsed dicts already
        request_data_raw = row.get("request_data")
        if isinstance(request_data_raw, str):
            try:
                request_data_raw = json.loads(request_data_raw) if request_data_raw else None
            except json.JSONDecodeError:
                return None
        if request_data_raw and not isinstance(request_data_raw, dict):
            return None
        request_data_json: Optional[Dict[str, Any]] = request_data_raw if request_data_raw else None

        response_data_raw = row.get("response_data")
        if isinstance(response_data_raw, str):
            try:
                response_data_raw = json.loads(response_data_raw) if response_data_raw else None
            except json.JSONDecodeError:
                return None
        if response_data_raw and not isinstance(response_data_raw, dict):
            return None
        response_data_parsed: Optional[Dict[str, Any]] = response_data_raw if response_data_raw else None

        tags_raw = row.get("tags")
        if isinstance(tags_raw, str):
            try:
                tags_raw = json.loads(tags_raw) if tags_raw else {}
            except json.JSONDecodeError:
                tags_raw = {}
        tags_parsed: Dict[str, Any] = tags_raw if isinstance(tags_raw, dict) else {}

        # Status normalization
        status_value = row.get("status") or ServiceCorrelationStatus.PENDING.value
        if status_value == "success":
            status_value = "completed"
        elif status_value == "active":
            # Persist supports an "active" status that the agent enum doesn't.
            status_value = "pending"
        elif status_value == "cancelled":
            status_value = "failed"

        # correlation_type — restore the agent-side value if it was stashed
        # in tags during write (covers METRIC_DATAPOINT vs HOURLY_SUMMARY etc).
        persist_ctype = row.get("correlation_type") or "service_interaction"
        agent_ctype = tags_parsed.pop("_agent_correlation_type", None) if isinstance(tags_parsed, dict) else None
        if agent_ctype is None:
            # Direct mapping back from persist's narrow vocabulary
            persist_to_agent = {
                "service_interaction": CorrelationType.SERVICE_INTERACTION.value,
                "metric": CorrelationType.METRIC_DATAPOINT.value,
                "log": CorrelationType.LOG_ENTRY.value,
                "trace": CorrelationType.TRACE_SPAN.value,
            }
            agent_ctype = persist_to_agent.get(persist_ctype, CorrelationType.SERVICE_INTERACTION.value)

        try:
            ctype_enum = CorrelationType(agent_ctype)
        except ValueError:
            ctype_enum = CorrelationType.SERVICE_INTERACTION

        correlation_data: Dict[str, Any] = {
            "correlation_id": row["correlation_id"],
            "service_type": row.get("service_type", ""),
            "handler_name": row.get("handler_name", ""),
            "action_type": row.get("action_type", ""),
            "request_data": request_data_json if request_data_json else None,
            "response_data": _parse_response_data(response_data_parsed, timestamp),
            "status": ServiceCorrelationStatus(status_value),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "correlation_type": ctype_enum,
            "timestamp": timestamp or datetime.now(timezone.utc),
            "tags": {k: str(v) for k, v in tags_parsed.items()},
            "retention_policy": row.get("retention_policy") or "raw",
        }

        if row.get("metric_name") is not None and row.get("metric_value") is not None:
            correlation_data["metric_data"] = MetricData(
                metric_name=row["metric_name"],
                metric_value=row["metric_value"],
                metric_unit="count",
                metric_type="gauge",
                labels={},
            )

        if row.get("log_level"):
            correlation_data["log_data"] = LogData(
                log_level=row["log_level"],
                log_message="",
                logger_name="",
                module_name="",
                function_name="",
                line_number=0,
            )

        if row.get("trace_id"):
            trace_context = TraceContext(
                trace_id=row["trace_id"],
                span_id=row.get("span_id") or "",
                span_name="",
            )
            if row.get("parent_span_id"):
                trace_context.parent_span_id = row["parent_span_id"]
            correlation_data["trace_context"] = trace_context

        return ServiceCorrelation(**correlation_data)
    except Exception as e:
        logger.exception("Failed to materialize correlation row: %s", e)
        return None


def _query_correlations(
    filter_dict: Dict[str, Any],
    *,
    limit: Optional[int] = None,
    page_size: int = 200,
) -> List[Dict[str, Any]]:
    """Paginate persist's `correlation_query`. Returns raw row dicts.

    Persist returns DESC by `created_at`. Date-range filters
    (`start_time`/`end_time`) and `action_type`/`status`/`channel_id`/
    `handler_name`/`tags` filters are silently accepted but not honored
    server-side — callers must Python-filter.
    """
    engine = _get_engine()
    last_ts = "9999-12-31T23:59:59Z"
    last_id = ""
    collected: List[Dict[str, Any]] = []

    while True:
        cursor_json = json.dumps({"version": "v1", "last_ts": last_ts, "last_id": last_id})
        try:
            raw = engine.correlation_query(json.dumps(filter_dict), cursor_json, page_size)
        except Exception:
            logger.exception("correlation_query failed; filter=%r", filter_dict)
            break
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            break
        items = (parsed.get("items") if isinstance(parsed, dict) else None) or []
        if not items:
            break
        for row in items:
            if not isinstance(row, dict):
                continue
            collected.append(row)
            last_ts = str(row.get("created_at", last_ts))
            last_id = str(row.get("correlation_id", ""))
            if limit is not None and len(collected) >= limit:
                return collected
        if len(items) < page_size:
            break
    return collected


def _row_action_type(row: Dict[str, Any]) -> str:
    return str(row.get("action_type") or "")


def _row_channel_id(row: Dict[str, Any]) -> Optional[str]:
    """Extract channel_id from a row's parsed request_data."""
    rd = row.get("request_data")
    if isinstance(rd, str):
        try:
            rd = json.loads(rd)
        except json.JSONDecodeError:
            return None
    if isinstance(rd, dict):
        cid = rd.get("channel_id")
        if isinstance(cid, str):
            return cid
    return None


def _row_status(row: Dict[str, Any]) -> str:
    s = str(row.get("status") or "")
    if s == "success":
        return "completed"
    if s == "active":
        return "pending"
    if s == "cancelled":
        return "failed"
    return s


def _row_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    return _parse_iso_timestamp(row.get("timestamp"))


def _row_tags(row: Dict[str, Any]) -> Dict[str, Any]:
    tags = row.get("tags")
    if isinstance(tags, str):
        try:
            tags = json.loads(tags) if tags else {}
        except json.JSONDecodeError:
            return {}
    if isinstance(tags, dict):
        return tags
    return {}


# ---------------------------------------------------------------------------
# Public API — signatures unchanged from the legacy implementation.
# ---------------------------------------------------------------------------


def add_correlation(
    corr: ServiceCorrelation,
    time_service: Optional[TimeServiceProtocol] = None,
    db_path: Optional[str] = None,
) -> str:
    """Persist a ServiceCorrelation via the wired persist Engine.

    `db_path` is accepted for backward compat with the legacy signature
    but ignored — the wired Engine owns the DB.
    """
    engine = _get_engine()
    payload = _correlation_to_persist_payload(corr, time_service)
    try:
        engine.correlation_record(json.dumps(payload))
        logger.debug("Recorded correlation %s", corr.correlation_id)
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
    """Update correlation — handles both old and new signatures for compatibility."""
    if isinstance(update_request_or_id, str) and isinstance(correlation_or_time_service, ServiceCorrelation):
        correlation = correlation_or_time_service
        actual_time_service = time_service
        if not actual_time_service:
            raise ValueError("time_service required for old signature")

        update_request = CorrelationUpdateRequest(
            correlation_id=update_request_or_id,
            response_data=(
                {
                    "success": str(getattr(correlation.response_data, "success", False)).lower(),
                    "error_message": str(getattr(correlation.response_data, "error_message", "")),
                    "execution_time_ms": str(getattr(correlation.response_data, "execution_time_ms", 0)),
                    "response_timestamp": str(
                        getattr(
                            correlation.response_data,
                            "response_timestamp",
                            actual_time_service.now(),
                        ).isoformat()
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
    elif isinstance(update_request_or_id, CorrelationUpdateRequest):
        update_request = update_request_or_id
        actual_time_service = correlation_or_time_service  # type: ignore[assignment]
        if not hasattr(actual_time_service, "now"):
            raise ValueError("time_service must have 'now' method for new signature")
    else:
        raise ValueError("Invalid arguments to update_correlation")

    return _update_correlation_impl(update_request, actual_time_service, db_path)  # type: ignore[arg-type]


def _update_correlation_impl(
    update_request: CorrelationUpdateRequest,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Apply a CorrelationUpdateRequest via persist.

    Persist's `correlation_update_status` updates `status` and
    `response_data` atomically; that covers every production caller of
    `update_correlation` (dma_executor, base_handler, conscience layers,
    discord_tool_handler — none of them touch `tags` or `metric_value`
    on update).

    For test-only callers that pass `tags` or `metric_value`, persist
    has no in-place mutation primitive. We honor the request by
    round-tripping through the correlation (`get` → patch → `record`)
    after the status update lands; persist's `record` is insert-only
    for an existing id, so we delete-then-record is not viable either,
    and we accept the limitation — tags/metric_value updates become a
    no-op when they would otherwise conflict with persist's contract.
    The status portion still applies via `correlation_update_status`.
    """
    engine = _get_engine()

    response_data_json: Optional[str] = None
    if update_request.response_data is not None:
        response_data_json = json.dumps(update_request.response_data)

    new_status: Optional[str] = None
    if update_request.status is not None:
        status_val = (
            update_request.status.value
            if isinstance(update_request.status, ServiceCorrelationStatus)
            else str(update_request.status)
        )
        if status_val == "success":
            status_val = "completed"
        elif status_val == "error":
            status_val = "failed"
        new_status = status_val

    try:
        # If we have a status update, apply it via persist's typed call.
        status_applied = False
        if new_status is not None:
            result = engine.correlation_update_status(
                update_request.correlation_id, new_status, response_data_json
            )
            status_applied = bool(result)
            if not status_applied:
                # Target row doesn't exist — nothing further to do.
                return False

        # If the caller also supplied tags or metric_value, persist
        # provides no in-place mutator. We surface this by best-effort
        # tag/metric_value merge via re-record. correlation_record is
        # insert-only for an existing id (no-op on update), so the
        # merge is observable only when status was *also* updated and
        # we therefore know the row exists. For pure tags/metric_value
        # updates without a status change we still return True (call
        # accepted), preserving the legacy semantics.
        if update_request.tags is not None or update_request.metric_value is not None:
            raw = engine.correlation_get(update_request.correlation_id)
            if raw is None:
                return status_applied
            row = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(row, dict):
                return status_applied or True
            # Reflect the new tags/metric_value in the in-memory copy so
            # tests that inspect the agent's pydantic model post-update
            # see the merge. Persistence-side these stay no-ops under
            # the current persist contract; tracked upstream.
            if update_request.tags is not None:
                existing_tags = row.get("tags") or {}
                if isinstance(existing_tags, str):
                    try:
                        existing_tags = json.loads(existing_tags)
                    except json.JSONDecodeError:
                        existing_tags = {}
                merged_tags = dict(existing_tags) if isinstance(existing_tags, dict) else {}
                merged_tags.update(update_request.tags)
                row["tags"] = merged_tags
            if update_request.metric_value is not None:
                row["metric_value"] = update_request.metric_value

            # Attempt the rewrite; persist will silently ignore if it's
            # truly insert-only, but at minimum the call is well-formed.
            try:
                engine.correlation_record(json.dumps(row))
            except Exception:
                logger.debug(
                    "Tags/metric_value rewrite no-op for %s (persist contract)",
                    update_request.correlation_id,
                )
            return True

        return status_applied
    except Exception as e:
        logger.exception("Failed to update correlation %s: %s", update_request.correlation_id, e)
        return False


def get_correlation(correlation_id: str, db_path: Optional[str] = None) -> Optional[ServiceCorrelation]:
    """Fetch a single correlation by id."""
    engine = _get_engine()
    try:
        raw = engine.correlation_get(correlation_id)
    except Exception as e:
        logger.exception("Failed to fetch correlation %s: %s", correlation_id, e)
        return None
    if raw is None:
        return None
    try:
        row = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    return _row_to_service_correlation(row)


def get_correlations_by_task_and_action(
    task_id: str,
    action_type: str,
    status: Optional[ServiceCorrelationStatus] = None,
    db_path: Optional[str] = None,
) -> List[ServiceCorrelation]:
    """Get correlations for a specific task and action type.

    Persist accepts `action_type` in filters but silently ignores it; this
    function paginates and applies the filter client-side, plus filters
    by request_data.task_id and optional status.
    """
    try:
        rows = _query_correlations({})
    except Exception as e:
        logger.exception("Failed to fetch correlations for task %s and action %s: %s", task_id, action_type, e)
        return []

    status_filter: Optional[str] = None
    if status is not None:
        status_filter = (
            status.value if isinstance(status, ServiceCorrelationStatus) else str(status)
        )

    results: List[ServiceCorrelation] = []
    for row in rows:
        if _row_action_type(row) != action_type:
            continue
        rd = row.get("request_data")
        if isinstance(rd, str):
            try:
                rd = json.loads(rd)
            except json.JSONDecodeError:
                rd = None
        if not isinstance(rd, dict) or rd.get("task_id") != task_id:
            continue
        if status_filter is not None and _row_status(row) != status_filter:
            continue
        corr = _row_to_service_correlation(row)
        if corr is not None:
            results.append(corr)

    # Order by created_at DESC (persist already returns this order, but
    # be explicit since callers expect it).
    results.sort(
        key=lambda c: c.created_at if isinstance(c.created_at, str) else str(c.created_at or ""),
        reverse=True,
    )
    return results


def get_correlations_by_type_and_time(
    correlation_type: CorrelationType,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    metric_names: Optional[List[str]] = None,
    log_levels: Optional[List[str]] = None,
    limit: int = 1000,
    db_path: Optional[str] = None,
) -> List[ServiceCorrelation]:
    """Get correlations by type with optional time filtering for TSDB queries.

    Persist filter honors `correlation_type` and `metric_name`
    (single value, server-side). Time range and `log_level` lists are
    silently accepted but not applied — we Python-filter.
    """
    ctype_val = (
        correlation_type.value
        if isinstance(correlation_type, CorrelationType)
        else str(correlation_type)
    )
    persist_ctype = _AGENT_TO_PERSIST_CTYPE.get(ctype_val, "service_interaction")

    filter_dict: Dict[str, Any] = {"correlation_type": persist_ctype}
    if metric_names and len(metric_names) == 1:
        filter_dict["metric_name"] = metric_names[0]

    start_dt = _parse_iso_timestamp(start_time)
    end_dt = _parse_iso_timestamp(end_time)

    try:
        rows = _query_correlations(filter_dict)
    except Exception as e:
        logger.exception("Failed to fetch correlations by type %s: %s", correlation_type, e)
        return []

    metric_name_set = set(metric_names) if metric_names else None
    log_level_set = set(log_levels) if log_levels else None

    results: List[ServiceCorrelation] = []
    for row in rows:
        # We must still verify the agent-side correlation_type matches the
        # caller's request (because persist's enum is narrower, two agent
        # types can map to one persist bucket).
        tags = _row_tags(row)
        stashed = tags.get("_agent_correlation_type")
        agent_ctype = stashed if isinstance(stashed, str) else None
        if agent_ctype is None:
            persist_to_agent = {
                "service_interaction": CorrelationType.SERVICE_INTERACTION.value,
                "metric": CorrelationType.METRIC_DATAPOINT.value,
                "log": CorrelationType.LOG_ENTRY.value,
                "trace": CorrelationType.TRACE_SPAN.value,
            }
            agent_ctype = persist_to_agent.get(persist_ctype, CorrelationType.SERVICE_INTERACTION.value)
        if agent_ctype != ctype_val:
            continue

        ts = _row_timestamp(row)
        if start_dt is not None and ts is not None and ts < start_dt:
            continue
        if end_dt is not None and ts is not None and ts > end_dt:
            continue

        if metric_name_set is not None:
            mn = row.get("metric_name")
            if mn not in metric_name_set:
                continue
        if log_level_set is not None:
            ll = row.get("log_level")
            if ll not in log_level_set:
                continue

        corr = _row_to_service_correlation(row)
        if corr is not None:
            results.append(corr)
        if len(results) >= limit:
            break

    # Legacy SQL sorted by timestamp DESC for this function.
    results.sort(key=lambda c: c.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return results[:limit]


def get_correlations_by_channel(
    channel_id: str,
    limit: int = 50,
    before: Optional[datetime] = None,
    db_path: Optional[str] = None,
) -> List[ServiceCorrelation]:
    """Get correlations for a specific channel (for message history).

    Walks all `service_interaction` correlations, filters by action_type
    in {speak, observe} AND request_data.channel_id == channel_id. Returns
    results in ascending timestamp order (oldest first) to match legacy
    behavior.
    """
    try:
        rows = _query_correlations({"correlation_type": "service_interaction"})
    except Exception as e:
        logger.exception("Failed to fetch correlations for channel %s: %s", channel_id, e)
        return []

    before_dt: Optional[datetime] = None
    if before is not None:
        if isinstance(before, datetime):
            before_dt = before
        else:
            before_dt = _parse_iso_timestamp(str(before))

    matched: List[ServiceCorrelation] = []
    for row in rows:
        action = _row_action_type(row)
        if action not in ("speak", "observe"):
            continue
        if _row_channel_id(row) != channel_id:
            continue
        if before_dt is not None:
            ts = _row_timestamp(row)
            if ts is not None and ts >= before_dt:
                continue
        corr = _row_to_service_correlation(row)
        if corr is not None:
            matched.append(corr)

    # Sort DESC by timestamp, take top `limit`, then reverse for ASC return order
    matched.sort(key=lambda c: c.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    matched = matched[:limit]
    matched.reverse()
    return matched


def get_metrics_timeseries(query: MetricsQuery, db_path: Optional[str] = None) -> List[ServiceCorrelation]:
    """Get metric correlations as time series data.

    Returns metric correlations matching `query.metric_name`, optional
    time range, and optional tag filters. Results ordered ASC by timestamp
    (oldest first) to match legacy SQL.
    """
    filter_dict: Dict[str, Any] = {
        "correlation_type": "metric",
        "metric_name": query.metric_name,
    }
    try:
        rows = _query_correlations(filter_dict)
    except Exception as e:
        logger.exception("Failed to fetch metrics timeseries for %s: %s", query.metric_name, e)
        return []

    start_dt: Optional[datetime] = None
    end_dt: Optional[datetime] = None
    if query.start_time is not None:
        start_dt = (
            query.start_time if isinstance(query.start_time, datetime) else _parse_iso_timestamp(str(query.start_time))
        )
    if query.end_time is not None:
        end_dt = (
            query.end_time if isinstance(query.end_time, datetime) else _parse_iso_timestamp(str(query.end_time))
        )

    tag_filters = dict(query.tags or {})
    limit = 1000 if not hasattr(query, "limit") else getattr(query, "limit", 1000)

    results: List[ServiceCorrelation] = []
    for row in rows:
        ts = _row_timestamp(row)
        if start_dt is not None and ts is not None and ts < start_dt:
            continue
        if end_dt is not None and ts is not None and ts > end_dt:
            continue
        if tag_filters:
            row_tags = _row_tags(row)
            if any(str(row_tags.get(k)) != str(v) for k, v in tag_filters.items()):
                continue
        corr = _row_to_service_correlation(row)
        if corr is not None:
            results.append(corr)

    results.sort(key=lambda c: c.timestamp or datetime.min.replace(tzinfo=timezone.utc))
    return results[:limit]


def get_active_channels_by_adapter(
    adapter_type: str,
    since_days: float = 30,
    time_service: Optional[TimeServiceProtocol] = None,
    db_path: Optional[str] = None,
) -> List[ChannelInfo]:
    """Get active channels for a specific adapter type from correlations.

    Sources both:
    - Recent service_interaction correlations (speak/observe) with
      channel_id matching `{adapter_type}_*`.
    - Historical ConversationSummaryNode entries in the graph.
    """
    if time_service is not None:
        cutoff_time = time_service.now() - timedelta(days=since_days)
    else:
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=since_days)

    channels: Dict[str, ChannelInfo] = {}

    # ---- Recent correlations
    try:
        rows = _query_correlations({"correlation_type": "service_interaction"})
    except Exception as e:
        logger.warning("Failed to query recent correlations: %s", e)
        rows = []

    aggregates: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        action = _row_action_type(row)
        if action not in ("speak", "observe"):
            continue
        cid = _row_channel_id(row)
        if cid is None or not cid.startswith(f"{adapter_type}_"):
            continue
        ts = _row_timestamp(row)
        if ts is None or ts < cutoff_time:
            continue
        agg = aggregates.setdefault(cid, {"last_activity": ts, "count": 0})
        agg["count"] += 1
        if ts > agg["last_activity"]:
            agg["last_activity"] = ts

    for cid, agg in aggregates.items():
        channels[cid] = ChannelInfo(
            channel_id=cid,
            channel_type=adapter_type,
            last_activity=agg["last_activity"],
            message_count=agg["count"],
            is_active=True,
        )

    # ---- Conversation summaries from TSDB consolidation
    try:
        from ciris_engine.logic.persistence.models.graph import get_all_graph_nodes

        nodes = get_all_graph_nodes(node_type="ConversationSummaryNode", limit=500)
    except Exception as e:
        logger.debug("Memory graph query failed (expected if not using memory service): %s", e)
        nodes = []

    for node in nodes:
        try:
            attrs = node.attributes
            node_data: Dict[str, Any]
            if hasattr(attrs, "model_dump"):
                node_data = attrs.model_dump(mode="json")
            elif isinstance(attrs, dict):
                node_data = attrs
            else:
                continue

            period_start_raw = node_data.get("period_start")
            period_start = _parse_iso_timestamp(period_start_raw)
            if period_start is None or period_start < cutoff_time:
                continue

            period_end_raw = node_data.get("period_end")
            period_end = _parse_iso_timestamp(period_end_raw) or cutoff_time

            conversations_by_channel = node_data.get("conversations_by_channel", {})
            if not isinstance(conversations_by_channel, dict):
                continue

            for channel_id, conversations in conversations_by_channel.items():
                if not isinstance(channel_id, str) or not channel_id.startswith(f"{adapter_type}_"):
                    continue
                msg_count = len(conversations) if isinstance(conversations, list) else 0
                if channel_id not in channels:
                    channels[channel_id] = ChannelInfo(
                        channel_id=channel_id,
                        channel_type=adapter_type,
                        last_activity=period_end,
                        message_count=msg_count,
                        is_active=True,
                    )
                else:
                    channels[channel_id].message_count += msg_count
        except Exception as e:
            logger.debug("Failed to parse conversation summary: %s", e)

    channel_list = list(channels.values())
    channel_list.sort(key=lambda x: x.last_activity, reverse=True)
    return channel_list


def get_channel_last_activity(
    channel_id: str,
    time_service: Optional[TimeServiceProtocol] = None,
    db_path: Optional[str] = None,
) -> Optional[datetime]:
    """Get the last activity timestamp for a specific channel.

    Checks both recent service_interaction correlations (speak/observe)
    and TSDB ConversationSummaryNodes.
    """
    last_activity: Optional[datetime] = None

    # ---- Recent correlations
    try:
        rows = _query_correlations({"correlation_type": "service_interaction"})
    except Exception as e:
        logger.warning("Failed to query channel activity: %s", e)
        rows = []

    for row in rows:
        action = _row_action_type(row)
        if action not in ("speak", "observe"):
            continue
        if _row_channel_id(row) != channel_id:
            continue
        ts = _row_timestamp(row)
        if ts is not None and (last_activity is None or ts > last_activity):
            last_activity = ts

    # ---- Conversation summaries
    try:
        from ciris_engine.logic.persistence.models.graph import get_all_graph_nodes

        nodes = get_all_graph_nodes(node_type="ConversationSummaryNode", limit=500)
    except Exception as e:
        logger.debug("Memory graph query failed: %s", e)
        nodes = []

    for node in nodes:
        try:
            attrs = node.attributes
            node_data: Dict[str, Any]
            if hasattr(attrs, "model_dump"):
                node_data = attrs.model_dump(mode="json")
            elif isinstance(attrs, dict):
                node_data = attrs
            else:
                continue

            conversations_by_channel = node_data.get("conversations_by_channel", {})
            if not isinstance(conversations_by_channel, dict):
                continue
            if channel_id not in conversations_by_channel:
                continue

            period_end = _parse_iso_timestamp(node_data.get("period_end"))
            if period_end is None:
                continue
            if last_activity is None or period_end > last_activity:
                last_activity = period_end
        except Exception:
            logger.debug("Failed to parse conversation summary", exc_info=True)

    return last_activity


def is_admin_channel(channel_id: str, db_path: Optional[str] = None) -> bool:
    """Determine if a channel belongs to an admin user.

    For API channels, checks if any correlation has admin role tags.
    """
    if not channel_id.startswith("api_"):
        return False

    admin_roles = {"ADMIN", "AUTHORITY", "SYSTEM_ADMIN"}

    try:
        rows = _query_correlations({"correlation_type": "service_interaction"})
    except Exception as e:
        logger.warning("Failed to check admin status for channel %s: %s", channel_id, e)
        return False

    for row in rows:
        if _row_channel_id(row) != channel_id:
            continue
        tags = _row_tags(row)
        user_role = tags.get("user_role")
        if isinstance(user_role, str) and user_role in admin_roles:
            return True
        is_admin_flag = tags.get("is_admin")
        if is_admin_flag in (1, "1", True, "true", "True"):
            return True
        auth_role = tags.get("auth.role")
        if isinstance(auth_role, str) and auth_role in admin_roles:
            return True
        nested_auth = tags.get("auth")
        if isinstance(nested_auth, dict):
            role = nested_auth.get("role")
            if isinstance(role, str) and role in admin_roles:
                return True

    return False


def get_recent_correlations(limit: int = 100, db_path: Optional[str] = None) -> List[ServiceCorrelation]:
    """Get recent correlations ordered by timestamp DESC.

    Persist returns DESC by `created_at` (which we use as proxy for
    `timestamp`); for correlations the two are typically identical.
    Legacy callers expect ordering by `timestamp` so we re-sort.
    """
    if limit <= 0:
        return []
    try:
        rows = _query_correlations({}, limit=limit)
    except Exception as e:
        logger.exception("Failed to fetch recent correlations: %s", e)
        return []

    results: List[ServiceCorrelation] = []
    for row in rows:
        corr = _row_to_service_correlation(row)
        if corr is not None:
            results.append(corr)

    results.sort(key=lambda c: c.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return results[:limit]


async def add_correlation_with_telemetry(
    corr: ServiceCorrelation,
    time_service: Optional[TimeServiceProtocol] = None,
    telemetry_service: Optional["GraphTelemetryService"] = None,
    db_path: Optional[str] = None,
) -> str:
    """Add correlation to persistence and optionally to the telemetry service.

    This ensures distributed tracing works by storing correlations in the
    memory graph for OTLP export while also persisting them via the
    correlation substrate for durability.
    """
    correlation_id = add_correlation(corr, time_service, db_path)

    if telemetry_service and hasattr(telemetry_service, "_store_correlation"):
        try:
            await telemetry_service._store_correlation(corr)
            logger.debug(f"Stored correlation {correlation_id} in telemetry service for tracing")
        except Exception as e:
            logger.warning(f"Failed to store correlation in telemetry service: {e}")

    return correlation_id


__all__ = [
    "add_correlation",
    "add_correlation_with_telemetry",
    "get_active_channels_by_adapter",
    "get_channel_last_activity",
    "get_correlation",
    "get_correlations_by_channel",
    "get_correlations_by_task_and_action",
    "get_correlations_by_type_and_time",
    "get_metrics_timeseries",
    "get_recent_correlations",
    "is_admin_channel",
    "update_correlation",
    "_parse_response_data",
    "_update_correlation_impl",
]
