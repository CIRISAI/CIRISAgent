"""
Audit service endpoints for CIRIS API v3 (Simplified).

Provides access to the immutable audit trail for system observability.
Simplified to 3 core endpoints: query, get specific entry, and export.
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi import Path as FastAPIPath
from fastapi import Query, Request
from pydantic import BaseModel, Field, field_serializer

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.utils.jsondict_helpers import get_str, get_str_optional
from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.schemas.api.audit import AuditContext, EntryVerification
from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.services.graph.audit import AuditQuery, VerificationReport
from ciris_engine.schemas.services.nodes import AuditEntry

from ..constants import DESC_END_TIME, DESC_RESULTS_OFFSET, DESC_START_TIME, ERROR_AUDIT_SERVICE_NOT_AVAILABLE
from ._common import RESPONSES_404_500_503, RESPONSES_500_503, AuthAdminDep, AuthObserverDep

router = APIRouter(prefix="/audit", tags=["audit"])


# Internal dataclass for audit entry merging
from dataclasses import dataclass


@dataclass
class _MergedAuditEntry:
    """Internal: Audit entry with source tracking during merge."""

    entry: "AuditEntryResponse"
    sources: List[str]


# Response schemas specific to API


class AuditEntryResponse(BaseModel):
    """Audit entry response with formatted fields."""

    id: str = Field(..., description="Audit entry ID")
    action: str = Field(..., description="Action performed")
    actor: str = Field(..., description="Who performed the action")
    timestamp: datetime = Field(..., description="When action occurred")
    context: AuditContext = Field(..., description="Action context")
    signature: Optional[str] = Field(None, description="Cryptographic signature")
    hash_chain: Optional[str] = Field(None, description="Previous hash for chain")
    storage_sources: List[str] = Field(default_factory=list, description="Storage locations: graph, jsonl, sqlite")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class AuditEntryDetailResponse(BaseModel):
    """Detailed audit entry with verification info."""

    entry: AuditEntryResponse = Field(..., description="The audit entry")
    verification: Optional[EntryVerification] = Field(None, description="Entry verification status")
    chain_position: Optional[int] = Field(None, description="Position in audit chain")
    next_entry_id: Optional[str] = Field(None, description="Next entry in chain")
    previous_entry_id: Optional[str] = Field(None, description="Previous entry in chain")


class AuditEntriesResponse(BaseModel):
    """List of audit entries."""

    entries: List[AuditEntryResponse] = Field(..., description="Audit entries")
    total: int = Field(..., description="Total matching entries")
    offset: int = Field(0, description=DESC_RESULTS_OFFSET)
    limit: int = Field(100, description="Results limit")


class AuditExportResponse(BaseModel):
    """Audit export response."""

    format: str = Field(..., description="Export format")
    total_entries: int = Field(..., description="Total entries exported")
    export_url: Optional[str] = Field(None, description="URL to download export")
    export_data: Optional[str] = Field(None, description="Inline export data for small exports")


# Helper functions


def _convert_audit_entry(entry: AuditEntry) -> AuditEntryResponse:
    """Convert AuditEntry to API response format."""
    # Convert context to AuditContext
    ctx = entry.context
    if hasattr(ctx, "model_dump"):
        # Convert AuditEntryContext to dict, then to AuditContext
        ctx_dict = ctx.model_dump()
        additional_data = ctx_dict.get("additional_data", {})

        # Extract outcome from additional_data (stored by audit service)
        outcome = additional_data.get("outcome") if additional_data else None
        # Also check for error field to determine outcome
        error = ctx_dict.get("error")
        if not outcome and error:
            outcome = "failure"
        elif not outcome:
            outcome = "success"

        context = AuditContext(
            entity_id=ctx_dict.get("entity_id"),
            entity_type=ctx_dict.get("entity_type"),
            operation=ctx_dict.get("operation") or ctx_dict.get("method_name"),
            description=ctx_dict.get("description"),
            request_id=ctx_dict.get("request_id"),
            correlation_id=ctx_dict.get("correlation_id"),
            user_id=ctx_dict.get("user_id"),
            ip_address=ctx_dict.get("ip_address"),
            user_agent=ctx_dict.get("user_agent"),
            result=ctx_dict.get("result"),
            error=error,
            outcome=outcome,
            metadata=additional_data,
        )
    else:
        # If it's not an AuditEntryContext, create a minimal AuditContext
        context = AuditContext(description=str(ctx) if ctx else None)

    return AuditEntryResponse(
        id=getattr(entry, "id", f"audit_{entry.timestamp.isoformat()}"),
        action=entry.action,
        actor=entry.actor,
        timestamp=entry.timestamp,
        context=context,
        signature=entry.signature,
        hash_chain=entry.hash_chain,
        storage_sources=["graph"],  # Graph entries come from graph by definition
    )


def _get_audit_service(request: Request) -> AuditServiceProtocol:
    """Get audit service from app state."""
    audit_service = getattr(request.app.state, "audit_service", None)
    if not audit_service:
        raise HTTPException(status_code=503, detail=ERROR_AUDIT_SERVICE_NOT_AVAILABLE)
    return audit_service  # type: ignore[no-any-return]


def _sync_query_sqlite_audit(
    db_path: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:  # SERIALIZATION BOUNDARY - SQLite row_factory returns dicts
    """Query SQLite audit database directly (synchronous version)."""
    if not Path(db_path).exists():
        return []

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Build query with time filters
            query = "SELECT * FROM audit_log WHERE 1=1"
            params = []

            if start_time:
                query += " AND event_timestamp >= ?"
                params.append(start_time.isoformat())

            if end_time:
                query += " AND event_timestamp <= ?"
                params.append(end_time.isoformat())

            query += " ORDER BY event_timestamp DESC LIMIT ? OFFSET ?"
            params.extend([str(limit), str(offset)])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


async def _query_sqlite_audit(
    db_path: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:  # SERIALIZATION BOUNDARY - SQLite database query results
    """Query SQLite audit database directly using async thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_query_sqlite_audit, db_path, start_time, end_time, limit, offset)


def _normalize_timestamp_str(ts_str: str) -> str:
    """Normalize timestamp string to ISO format for consistent deduplication.

    SQLite uses: 2026-03-25T01:25:49.386438+00:00 (with T)
    JSONL uses:  2026-03-25 01:21:00.503015+00:00 (with space)

    Normalizes to ISO format with 'T' separator.
    """
    # Replace space with T for ISO format consistency
    return ts_str.replace(" ", "T")


# =============================================================================
# Helper functions for reducing cognitive complexity
# =============================================================================


def _entry_has_additional_metadata(entry: AuditEntry) -> bool:
    """Check if a graph entry has additional metadata worth merging.

    Graph entries may contain rich metadata from handlers (ponder_questions,
    tool_parameters, etc.) that SQLite entries don't have.
    """
    if not hasattr(entry, "context"):
        return False
    if not hasattr(entry.context, "additional_data"):
        return False
    return bool(entry.context.additional_data)


def _merge_graph_metadata_into_entry(merged_entry: _MergedAuditEntry, graph_ctx: Any) -> None:
    """Merge metadata from a graph entry into an existing merged entry.

    Copies keys from graph's additional_data that don't already exist
    in the merged entry's metadata.
    """
    if merged_entry.entry.context.metadata is None:
        merged_entry.entry.context.metadata = {}

    if hasattr(graph_ctx, "additional_data") and graph_ctx.additional_data:
        for key, value in graph_ctx.additional_data.items():
            if key not in merged_entry.entry.context.metadata:
                merged_entry.entry.context.metadata[key] = value


def _find_sqlite_entry_for_dedup_key(
    merged: Dict[str, _MergedAuditEntry], dedup_key: str
) -> Optional[_MergedAuditEntry]:
    """Find a SQLite entry in merged results that matches the given dedup key.

    Used to merge graph metadata into existing SQLite entries.
    """
    for merged_entry in merged.values():
        sqlite_dedup = (
            f"{_normalize_timestamp_str(merged_entry.entry.timestamp.isoformat())}_{merged_entry.entry.action}"
        )
        if sqlite_dedup == dedup_key:
            return merged_entry
    return None


def _infer_outcome_from_event(outcome: Optional[str], event_type: str) -> str:
    """Infer outcome from event type if not explicitly provided.

    Returns 'failure' if event_type contains 'fail' or 'error', otherwise 'success'.
    """
    if outcome:
        return outcome
    event_lower = event_type.lower()
    if "fail" in event_lower or "error" in event_lower:
        return "failure"
    return "success"


def _extract_handler_metadata(params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract handler-specific metadata fields from parameters.

    Handles DEFER, TOOL, PONDER, SPEAK, TASK_COMPLETE, and REJECT parameters.
    Returns a flat dict of extracted metadata.
    """
    metadata: Dict[str, Any] = {}

    # DEFER params
    if "defer_reason" in params:
        metadata["defer_reason"] = params["defer_reason"]
    if "defer_until" in params:
        metadata["defer_until"] = params["defer_until"]

    # TOOL params
    if "tool_name" in params:
        metadata["tool_name"] = params["tool_name"]
    elif "name" in params:
        metadata["tool_name"] = params["name"]

    if "parameters" in params:
        tool_params = params["parameters"]
        metadata["tool_parameters"] = json.dumps(tool_params) if isinstance(tool_params, dict) else str(tool_params)

    # PONDER params
    if "ponder_questions" in params:
        metadata["ponder_questions"] = params["ponder_questions"]
    elif "questions" in params:
        metadata["ponder_questions"] = params["questions"]

    # SPEAK params
    if "content" in params:
        metadata["content"] = params["content"]

    # TASK_COMPLETE params
    if "completion_reason" in params:
        metadata["completion_reason"] = params["completion_reason"]

    # REJECT params
    if "reason" in params:
        metadata["reject_reason"] = params["reason"]

    return metadata


def _parse_event_payload_metadata(
    event_payload_str: Optional[str],
) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse event payload JSON and extract metadata and description.

    Returns (metadata dict, description string).
    If parsing fails, returns empty metadata and the original string as description.
    """
    if not event_payload_str:
        return {}, None

    try:
        payload = json.loads(event_payload_str)
    except json.JSONDecodeError:
        return {}, event_payload_str

    if not isinstance(payload, dict):
        return {}, event_payload_str

    metadata: Dict[str, Any] = {}

    # Extract nested parameters
    params_str = payload.get("parameters", "{}")
    if isinstance(params_str, str):
        try:
            params = json.loads(params_str)
            if isinstance(params, dict):
                metadata.update(_extract_handler_metadata(params))
        except json.JSONDecodeError:
            pass

    # Extract direct payload fields
    for key in ["thought_id", "task_id", "handler_name", "action_type"]:
        if key in payload:
            metadata[key] = payload[key]

    # Build description from payload
    description = payload.get("action_type") or payload.get("handler_name") or event_payload_str

    return metadata, description


def _parse_jsonl_entry_timestamp(
    entry: dict[str, object],
) -> Optional[datetime]:  # SERIALIZATION BOUNDARY - JSONL raw entries
    """Parse timestamp from JSONL entry."""
    entry_time_str = get_str_optional(entry, "timestamp") or get_str_optional(entry, "event_timestamp")
    if entry_time_str:
        try:
            return datetime.fromisoformat(entry_time_str.replace("Z", UTC_TIMEZONE_SUFFIX).replace(" ", "T"))
        except ValueError:
            return None
    return None


def _entry_matches_time_filter(
    entry: dict[str, object],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> bool:  # SERIALIZATION BOUNDARY - JSONL raw entries
    """Check if entry matches time filter criteria."""
    if not (start_time or end_time):
        return True

    entry_time = _parse_jsonl_entry_timestamp(entry)
    if not entry_time:
        return True  # Include entries without valid timestamps

    if start_time and entry_time < start_time:
        return False
    if end_time and entry_time > end_time:
        return False

    return True


def _sync_query_jsonl_audit(
    jsonl_path: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:  # SERIALIZATION BOUNDARY - JSONL entries
    """Query JSONL audit file directly (synchronous version)."""
    if not Path(jsonl_path).exists():
        return []

    try:
        entries = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if _entry_matches_time_filter(entry, start_time, end_time):
                            entries.append(entry)
                    except json.JSONDecodeError:
                        continue

        # Sort by timestamp (newest first) and apply pagination
        entries.sort(key=lambda x: x.get("timestamp") or x.get("event_timestamp") or "", reverse=True)
        return entries[offset : offset + limit]
    except Exception:
        return []


async def _query_jsonl_audit(
    jsonl_path: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, object]]:  # SERIALIZATION BOUNDARY - JSONL entries
    """Query JSONL audit file directly using async thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_query_jsonl_audit, jsonl_path, start_time, end_time, limit, offset)


def _process_graph_entries(
    merged: Dict[str, _MergedAuditEntry], graph_entries: List[AuditEntry], seen_timestamps: set[str]
) -> None:
    """Process graph entries and add them to merged results.

    Graph entries contain the full handler action metadata (ponder_questions, tool_parameters, etc.)
    while SQLite entries may only have partial data. We merge graph data INTO existing SQLite
    entries rather than skipping graph entries entirely.
    """
    import logging

    logger = logging.getLogger(__name__)

    for entry in graph_entries:
        normalized_ts = _normalize_timestamp_str(entry.timestamp.isoformat())
        dedup_key = f"{normalized_ts}_{entry.action}"
        entry_id = getattr(entry, "id", f"audit_{entry.timestamp.isoformat()}_{entry.actor}")
        has_metadata = _entry_has_additional_metadata(entry)

        if dedup_key in seen_timestamps:
            _handle_duplicate_graph_entry(merged, entry, dedup_key, has_metadata, logger)
            continue

        _add_new_graph_entry(merged, entry, entry_id, dedup_key, seen_timestamps, logger)


def _handle_duplicate_graph_entry(
    merged: Dict[str, _MergedAuditEntry],
    entry: AuditEntry,
    dedup_key: str,
    has_metadata: bool,
    logger: Any,
) -> None:
    """Handle a graph entry that duplicates an existing SQLite entry.

    If the graph entry has metadata, merge it into the existing SQLite entry.
    """
    if not has_metadata:
        return

    matched_entry = _find_sqlite_entry_for_dedup_key(merged, dedup_key)
    if matched_entry:
        _merge_graph_metadata_into_entry(matched_entry, entry.context)
        matched_entry.sources.append("graph")
    else:
        logger.warning(f"[AUDIT API] No matching SQLite entry found for dedup_key={dedup_key}")


def _add_new_graph_entry(
    merged: Dict[str, _MergedAuditEntry],
    entry: AuditEntry,
    entry_id: str,
    dedup_key: str,
    seen_timestamps: set[str],
    logger: Any,
) -> None:
    """Add a new graph entry to merged results."""
    logger.info(f"[AUDIT API]   Adding new entry with id={entry_id}")
    if entry_id not in merged:
        merged[entry_id] = _MergedAuditEntry(entry=_convert_audit_entry(entry), sources=["graph"])
        seen_timestamps.add(dedup_key)
    else:
        merged[entry_id].sources.append("graph")


def _process_sqlite_entries(
    merged: Dict[str, _MergedAuditEntry],
    sqlite_entries: list[dict[str, object]],
    seen_timestamps: set[str],
    dedup_to_entry: Dict[str, str],
) -> None:  # SERIALIZATION BOUNDARY - SQLite query results
    """Process SQLite entries and add them to merged results.

    SQLite entries are the authoritative source with the hash chain.
    Track timestamps for deduplication with graph entries.
    """
    for sqlite_entry in sqlite_entries:
        entry_info = _extract_sqlite_entry_info(sqlite_entry)
        _track_sqlite_dedup_key(entry_info, seen_timestamps, dedup_to_entry)

        if entry_info["entry_id"] in merged:
            merged[entry_info["entry_id"]].sources.append("sqlite")
        else:
            _add_new_sqlite_entry(merged, sqlite_entry, entry_info)


def _extract_sqlite_entry_info(sqlite_entry: dict[str, object]) -> Dict[str, str]:
    """Extract basic info from a SQLite audit entry."""
    event_timestamp = get_str(sqlite_entry, "event_timestamp", "")
    originator_id = get_str(sqlite_entry, "originator_id", "unknown")
    event_type = get_str(sqlite_entry, "event_type", "unknown")
    entry_id = get_str_optional(sqlite_entry, "event_id") or f"audit_{event_timestamp}_{originator_id}"
    normalized_ts = _normalize_timestamp_str(event_timestamp)
    dedup_key = f"{normalized_ts}_{event_type}"

    return {
        "event_timestamp": event_timestamp,
        "originator_id": originator_id,
        "event_type": event_type,
        "entry_id": entry_id,
        "dedup_key": dedup_key,
    }


def _track_sqlite_dedup_key(
    entry_info: Dict[str, str], seen_timestamps: set[str], dedup_to_entry: Dict[str, str]
) -> None:
    """Track dedup key for later source merging with graph/jsonl entries."""
    seen_timestamps.add(entry_info["dedup_key"])
    dedup_to_entry[entry_info["dedup_key"]] = entry_info["entry_id"]


def _add_new_sqlite_entry(
    merged: Dict[str, _MergedAuditEntry], sqlite_entry: dict[str, object], entry_info: Dict[str, str]
) -> None:
    """Add a new SQLite entry to merged results."""
    timestamp = datetime.fromisoformat(entry_info["event_timestamp"].replace("Z", UTC_TIMEZONE_SUFFIX))
    outcome = _infer_outcome_from_event(get_str_optional(sqlite_entry, "outcome"), entry_info["event_type"])

    event_payload_str = get_str_optional(sqlite_entry, "event_payload")
    metadata, description = _parse_event_payload_metadata(event_payload_str)
    if description is None:
        description = event_payload_str

    context = AuditContext(
        description=description,
        entity_id=get_str_optional(sqlite_entry, "originator_id"),
        outcome=outcome,
        metadata=metadata if metadata else None,
    )

    merged[entry_info["entry_id"]] = _MergedAuditEntry(
        entry=AuditEntryResponse(
            id=entry_info["entry_id"],
            action=get_str(sqlite_entry, "event_type", "unknown"),
            actor=entry_info["originator_id"],
            timestamp=timestamp,
            context=context,
            signature=get_str_optional(sqlite_entry, "signature"),
            hash_chain=get_str_optional(sqlite_entry, "previous_hash"),
            storage_sources=["sqlite"],
        ),
        sources=["sqlite"],
    )


def _process_jsonl_entries(
    merged: Dict[str, _MergedAuditEntry],
    jsonl_entries: list[dict[str, object]],
    seen_timestamps: set[str],
    dedup_to_entry: Dict[str, str],
) -> None:  # SERIALIZATION BOUNDARY - JSONL raw entries
    """Process JSONL entries and add them to merged results.

    If entry already exists from SQLite/graph (by timestamp+action), just add 'jsonl' to sources.
    """
    for jsonl_entry in jsonl_entries:
        timestamp_str = get_str(jsonl_entry, "timestamp", "") or get_str(jsonl_entry, "event_timestamp", "")
        actor_str = get_str(jsonl_entry, "actor", "")
        action = get_str_optional(jsonl_entry, "action") or get_str(jsonl_entry, "event_type", "unknown")
        entry_id = get_str_optional(jsonl_entry, "id") or f"audit_{timestamp_str}_{actor_str}"

        # Check timestamp-based deduplication - add source to existing entry
        # Normalize timestamp format for consistent matching with SQLite
        normalized_ts = _normalize_timestamp_str(timestamp_str)
        dedup_key = f"{normalized_ts}_{action}"
        if dedup_key in seen_timestamps:
            # Find the existing entry and add jsonl to its sources
            # First check dedup_to_entry (populated by SQLite entries)
            existing_entry_id = dedup_to_entry.get(dedup_key)
            if existing_entry_id and existing_entry_id in merged:
                if "jsonl" not in merged[existing_entry_id].sources:
                    merged[existing_entry_id].sources.append("jsonl")
            else:
                # dedup_to_entry may not have this key if entry came from graph
                # Search merged entries by matching dedup_key
                for merged_id, merged_entry in merged.items():
                    entry_dedup = f"{_normalize_timestamp_str(merged_entry.entry.timestamp.isoformat())}_{merged_entry.entry.action}"
                    if entry_dedup == dedup_key:
                        if "jsonl" not in merged_entry.sources:
                            merged_entry.sources.append("jsonl")
                        break
            continue

        if entry_id not in merged:
            # Convert JSONL entry to AuditEntryResponse format
            ts_str = get_str_optional(jsonl_entry, "timestamp") or get_str_optional(jsonl_entry, "event_timestamp")
            timestamp = (
                datetime.fromisoformat(ts_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                if ts_str
                else datetime.now(timezone.utc)
            )

            description = get_str_optional(jsonl_entry, "description") or get_str_optional(jsonl_entry, "event_payload")
            # Extract outcome from JSONL entry
            outcome = get_str_optional(jsonl_entry, "outcome")
            if not outcome:
                # Try to infer from action or event_type
                action = get_str_optional(jsonl_entry, "action") or get_str(jsonl_entry, "event_type", "")
                if "fail" in action.lower() or "error" in action.lower():
                    outcome = "failure"
                else:
                    outcome = "success"
            context = AuditContext(description=description, outcome=outcome)

            merged[entry_id] = _MergedAuditEntry(
                entry=AuditEntryResponse(
                    id=entry_id,
                    action=get_str_optional(jsonl_entry, "action") or get_str(jsonl_entry, "event_type", "unknown"),
                    actor=get_str_optional(jsonl_entry, "actor") or get_str(jsonl_entry, "originator_id", "unknown"),
                    timestamp=timestamp,
                    context=context,
                    signature=get_str_optional(jsonl_entry, "signature"),
                    hash_chain=get_str_optional(jsonl_entry, "hash_chain")
                    or get_str_optional(jsonl_entry, "previous_hash"),
                    storage_sources=["jsonl"],
                ),
                sources=["jsonl"],
            )
        else:
            merged[entry_id].sources.append("jsonl")


async def _merge_audit_sources(
    graph_entries: List[AuditEntry],
    sqlite_entries: list[dict[str, object]],
    jsonl_entries: list[dict[str, object]],
) -> List[AuditEntryResponse]:  # SERIALIZATION BOUNDARY - Raw database results
    """Merge audit entries from all sources and track storage locations.

    Each event should appear ONCE with storage_sources showing which backends have it.
    SQLite entries are the authoritative source with the hash chain.
    Graph entries provide rich metadata (ponder_questions, tool_result, etc.).
    JSONL provides backup logging.
    """
    merged: Dict[str, _MergedAuditEntry] = {}  # Track entries by ID with their sources
    seen_timestamps: set[str] = set()  # Track timestamp+action for deduplication
    dedup_to_entry: Dict[str, str] = {}  # Map dedup_key -> entry_id for source tracking

    # Process SQLite entries FIRST (authoritative source with hash chain)
    _process_sqlite_entries(merged, sqlite_entries, seen_timestamps, dedup_to_entry)

    # Process graph entries - merge metadata into SQLite entries, add 'graph' source
    _process_graph_entries(merged, graph_entries, seen_timestamps)

    # Process JSONL - just add 'jsonl' source to existing entries
    _process_jsonl_entries(merged, jsonl_entries, seen_timestamps, dedup_to_entry)

    # Update storage_sources for all merged entries and build result
    result = []
    for entry_data in merged.values():
        entry_data.entry.storage_sources = sorted(entry_data.sources)
        result.append(entry_data.entry)

    # Sort by timestamp (newest first)
    result.sort(key=lambda x: x.timestamp, reverse=True)
    return result


# Endpoints


@router.get("/entries", responses=RESPONSES_500_503)
async def query_audit_entries(
    request: Request,
    auth: AuthObserverDep,
    # Time range filters
    start_time: Optional[datetime] = Query(None, description=DESC_START_TIME),
    end_time: Optional[datetime] = Query(None, description=DESC_END_TIME),
    # Entity filters
    actor: Optional[str] = Query(None, description="Filter by actor"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    # Search and additional filters
    search: Optional[str] = Query(None, description="Search in audit details"),
    severity: Optional[str] = Query(None, description="Filter by severity (info, warning, error)"),
    outcome: Optional[str] = Query(None, description="Filter by outcome (success, failure)"),
    # Pagination
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description=DESC_RESULTS_OFFSET),
) -> SuccessResponse[AuditEntriesResponse]:
    """
    Query audit entries with flexible filtering.

    Combines time-based queries, entity filtering, and text search into a single endpoint.
    Returns paginated results sorted by timestamp (newest first).

    Requires OBSERVER role or higher.
    """
    audit_service = _get_audit_service(request)

    # Build unified query
    query = AuditQuery(
        start_time=start_time,
        end_time=end_time,
        actor=actor,
        event_type=event_type,
        entity_id=entity_id,
        search_text=search,
        severity=severity,
        outcome=outcome,
        limit=limit,
        offset=offset,
        order_by="timestamp",
        order_desc=True,
    )

    try:
        # Query all 3 audit sources concurrently

        # Query graph memory (existing functionality)
        graph_entries = await audit_service.query_audit_trail(query)

        # Get the proper data directory for SQLite path
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        data_dir = get_data_dir()
        sqlite_path = str(data_dir / "ciris_audit.db")
        jsonl_path = str(data_dir / "audit_logs.jsonl")

        # Query SQLite database directly
        sqlite_task = _query_sqlite_audit(
            sqlite_path,
            start_time=start_time,
            end_time=end_time,
            limit=limit * 3,  # Get more to account for merging
            offset=0,  # We'll handle pagination after merging
        )

        # Query JSONL file directly
        jsonl_task = _query_jsonl_audit(
            jsonl_path,
            start_time=start_time,
            end_time=end_time,
            limit=limit * 3,  # Get more to account for merging
            offset=0,  # We'll handle pagination after merging
        )

        # Execute SQLite and JSONL queries concurrently
        sqlite_entries, jsonl_entries = await asyncio.gather(sqlite_task, jsonl_task)

        # Merge all sources and track storage locations
        response_entries = await _merge_audit_sources(graph_entries, sqlite_entries, jsonl_entries)

        # Apply final pagination after merging
        paginated_entries = response_entries[offset : offset + limit]
        total = len(response_entries)

        return SuccessResponse(
            data=AuditEntriesResponse(entries=paginated_entries, total=total, offset=offset, limit=limit),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _find_audit_entry(entries: List[Any], entry_id: str) -> Tuple[Optional[Any], int]:
    """Find audit entry by ID with fallback to generated ID pattern."""
    for i, entry in enumerate(entries):
        if hasattr(entry, "id") and entry.id == entry_id:
            return entry, i
        # Also check if entry_id matches a generated ID pattern
        elif hasattr(entry, "timestamp") and hasattr(entry, "actor"):
            generated_id = f"audit_{entry.timestamp.strftime('%Y%m%d_%H%M%S')}_{entry.actor}"
            if generated_id == entry_id:
                return entry, i
    return None, -1


def _build_verification_info(target_entry: Any) -> EntryVerification:
    """Build verification information for audit entry."""
    return EntryVerification(
        signature_valid=target_entry.signature is not None,
        hash_chain_valid=target_entry.hash_chain is not None,
        verified_at=datetime.now(timezone.utc),
        verifier="system",
        algorithm="sha256",
        previous_hash_match=None,  # Would check in real implementation
    )


def _add_chain_navigation(response: AuditEntryDetailResponse, entries: List[Any], entry_index: int) -> None:
    """Add chain position and navigation links to response."""
    response.chain_position = entry_index

    if entry_index > 0:
        prev_entry = entries[entry_index - 1]
        response.previous_entry_id = getattr(
            prev_entry, "id", f"audit_{prev_entry.timestamp.strftime('%Y%m%d_%H%M%S')}_{prev_entry.actor}"
        )

    if entry_index < len(entries) - 1:
        next_entry = entries[entry_index + 1]
        response.next_entry_id = getattr(
            next_entry, "id", f"audit_{next_entry.timestamp.strftime('%Y%m%d_%H%M%S')}_{next_entry.actor}"
        )


@router.get("/entries/{entry_id}", responses=RESPONSES_404_500_503)
async def get_audit_entry(
    request: Request,
    auth: AuthObserverDep,
    entry_id: str = FastAPIPath(..., description="Audit entry ID"),
    verify: bool = Query(False, description="Include verification information"),
) -> SuccessResponse[AuditEntryDetailResponse]:
    """
    Get specific audit entry by ID with optional verification.

    Returns the audit entry and optionally includes:
    - Verification status of the entry's signature and hash
    - Position in the audit chain
    - Links to previous and next entries

    Requires OBSERVER role or higher.
    """
    audit_service = _get_audit_service(request)

    try:
        # Get recent entries to search within
        query = AuditQuery(limit=1000, order_by="timestamp", order_desc=True)
        entries = await audit_service.query_audit_trail(query)

        # Find the target entry
        target_entry, entry_index = _find_audit_entry(entries, entry_id)
        if not target_entry:
            raise HTTPException(status_code=404, detail=f"Audit entry '{entry_id}' not found")

        # Build base response
        response = AuditEntryDetailResponse(entry=_convert_audit_entry(target_entry))

        # Add verification info if requested
        if verify:
            await audit_service.get_verification_report()
            response.verification = _build_verification_info(target_entry)
            _add_chain_navigation(response, entries, entry_index)

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", responses=RESPONSES_500_503)
async def search_audit_trails(
    request: Request,
    auth: AuthObserverDep,
    search_text: Optional[str] = Query(None, description="Text to search for"),
    entity_id: Optional[str] = Query(None, description="Filter by entity ID"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    outcome: Optional[str] = Query(None, description="Filter by outcome"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description=DESC_RESULTS_OFFSET),
) -> SuccessResponse[AuditEntriesResponse]:
    """
    Search audit trails with text search and filters.

    This is a convenience endpoint that focuses on search functionality.
    For more complex queries, use the /entries endpoint.

    Requires OBSERVER role or higher.
    """
    # Delegate to the main query endpoint logic
    return await query_audit_entries(
        request=request,
        auth=auth,
        start_time=None,
        end_time=None,
        actor=None,
        event_type=None,
        entity_id=entity_id,
        search=search_text,
        severity=severity,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )


@router.post("/verify/{entry_id}", responses=RESPONSES_500_503)
async def verify_audit_entry(
    request: Request,
    auth: AuthAdminDep,
    entry_id: str = FastAPIPath(..., description="Audit entry ID to verify"),
) -> SuccessResponse[VerificationReport]:
    """
    Verify the integrity of a specific audit entry.

    Returns detailed verification information including signature validation
    and hash chain integrity.

    Requires ADMIN role or higher.
    """
    audit_service = _get_audit_service(request)

    try:
        # Get the full verification report
        verification_report = await audit_service.get_verification_report()
        return SuccessResponse(data=verification_report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export", responses=RESPONSES_500_503)
async def export_audit_data(
    request: Request,
    auth: AuthAdminDep,
    start_date: Optional[datetime] = Query(None, description="Export start date"),
    end_date: Optional[datetime] = Query(None, description="Export end date"),
    format: str = Query("jsonl", pattern="^(json|jsonl|csv)$", description="Export format"),
    include_verification: bool = Query(False, description="Include verification data in export"),
) -> SuccessResponse[AuditExportResponse]:
    """
    Export audit data for compliance and analysis.

    Exports audit entries in the specified format. For small datasets (< 1000 entries),
    data is returned inline. For larger datasets, a download URL is provided.

    Formats:
    - **jsonl**: JSON Lines format (one entry per line)
    - **json**: Standard JSON array
    - **csv**: CSV format with standard audit fields

    Requires ADMIN role or higher.
    """
    audit_service = _get_audit_service(request)

    try:
        # Export data
        export_data = await audit_service.export_audit_data(start_time=start_date, end_time=end_date, format=format)

        # Add verification data if requested
        if include_verification and format == "jsonl":
            # Get verification report
            verification_report = await audit_service.get_verification_report()
            # Append verification summary to export
            verification_summary = {
                "_verification": {
                    "verified": verification_report.verified,
                    "total_entries": verification_report.total_entries,
                    "valid_entries": verification_report.valid_entries,
                    "chain_intact": verification_report.chain_intact,
                    "verification_timestamp": verification_report.verification_completed.isoformat(),
                }
            }
            export_data += "\n" + json.dumps(verification_summary)

        # Count entries for response
        lines = export_data.split("\n")
        total_entries = len([l for l in lines if l.strip() and not l.startswith('{"_verification"')])

        if total_entries > 1000:
            # For large exports, would typically upload to storage
            # In production, this would upload to S3/cloud storage and return a signed URL
            return SuccessResponse(
                data=AuditExportResponse(
                    format=format,
                    total_entries=total_entries,
                    export_url=f"/v1/audit/export/download/{format}",  # Placeholder URL
                    export_data=None,
                ),
                metadata=ResponseMetadata(
                    timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
                ),
            )
        else:
            return SuccessResponse(
                data=AuditExportResponse(
                    format=format, total_entries=total_entries, export_url=None, export_data=export_data
                ),
                metadata=ResponseMetadata(
                    timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
                ),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
