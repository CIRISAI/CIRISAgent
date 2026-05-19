"""Thoughts persistence — routed through ciris-persist substrate APIs.

Part of 2.9.0 T-lane migration (CIRISAgent#763 / CIRISPersist#58):
removes the second libsqlite writer on `ciris_engine.db` to stop the
B-tree corruption from shared WAL pages. Public function signatures
are preserved verbatim so callers across the codebase need no changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, cast

from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.audit.core import EventPayload
from ciris_engine.schemas.persistence.core import ThoughtSummary
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import FinalAction, Thought, ThoughtContext
from ciris_engine.schemas.services.graph.audit import AuditEventData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persist engine accessor + payload conversion helpers.
# ---------------------------------------------------------------------------


def _get_engine() -> Any:
    """Return the wired persist engine; raise if not yet bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any thoughts operation"
        )
    return engine


def _thought_to_persist_payload(thought: Thought) -> Dict[str, Any]:
    """Convert a Thought into the dict shape `engine.thought_upsert` accepts."""
    thought_dict = thought.model_dump(mode="json")
    payload: Dict[str, Any] = {
        "thought_id": thought.thought_id,
        "source_task_id": thought.source_task_id,
        "agent_occurrence_id": thought.agent_occurrence_id,
        "channel_id": thought.channel_id,
        "thought_type": (
            thought.thought_type.value
            if isinstance(thought.thought_type, ThoughtType)
            else thought.thought_type
        ),
        "status": (
            thought.status.value
            if isinstance(thought.status, ThoughtStatus)
            else thought.status
        ),
        "created_at": thought.created_at,
        "updated_at": thought.updated_at,
        "round_number": thought.round_number,
        "content": thought.content,
        "thought_depth": thought.thought_depth,
        "parent_thought_id": thought.parent_thought_id,
    }
    # Mirror preferred_language into context so load-time round-trips
    # correctly (Task is the record of truth, Thought inherits).
    ctx = thought_dict.get("context")
    if ctx is None and thought.preferred_language is not None:
        ctx = {}
    if ctx is not None:
        ctx = dict(ctx)
        if thought.preferred_language is not None and not ctx.get("preferred_language"):
            ctx["preferred_language"] = thought.preferred_language
        payload["context"] = ctx
    pn = thought_dict.get("ponder_notes")
    if pn is not None:
        payload["ponder_notes"] = pn
    fa = thought_dict.get("final_action")
    if fa is not None:
        payload["final_action"] = fa
    return payload


def _persist_row_to_thought(row: Dict[str, Any]) -> Thought:
    """Materialize a persist thought row into a Thought."""
    agent_occurrence_id = str(row.get("agent_occurrence_id", "default"))

    try:
        status: ThoughtStatus = ThoughtStatus(row.get("status", ThoughtStatus.PENDING.value))
    except ValueError:
        status = ThoughtStatus.PENDING

    try:
        thought_type: ThoughtType = ThoughtType(
            row.get("thought_type", ThoughtType.STANDARD.value)
        )
    except ValueError:
        thought_type = ThoughtType.STANDARD

    context: Optional[ThoughtContext] = None
    ctx_data = row.get("context")
    if isinstance(ctx_data, str):
        try:
            ctx_data = json.loads(ctx_data)
        except json.JSONDecodeError:
            ctx_data = None
    if isinstance(ctx_data, dict) and ctx_data:
        task_id = ctx_data.get("task_id")
        correlation_id = ctx_data.get("correlation_id")
        if task_id and correlation_id:
            try:
                context = ThoughtContext(
                    task_id=task_id,
                    channel_id=ctx_data.get("channel_id"),
                    round_number=ctx_data.get("round_number", 0),
                    depth=ctx_data.get("depth", 0),
                    parent_thought_id=ctx_data.get("parent_thought_id"),
                    correlation_id=correlation_id,
                    agent_occurrence_id=ctx_data.get(
                        "agent_occurrence_id", agent_occurrence_id
                    ),
                    preferred_language=ctx_data.get("preferred_language"),
                )
            except Exception:  # nosec B110 - corrupt rows tolerate context loss
                context = None

    ponder_notes: Optional[List[str]] = None
    p = row.get("ponder_notes")
    if isinstance(p, str):
        try:
            p = json.loads(p)
        except json.JSONDecodeError:
            p = None
    if isinstance(p, list):
        ponder_notes = [str(x) for x in p]

    final_action: Optional[FinalAction] = None
    f = row.get("final_action")
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except json.JSONDecodeError:
            f = None
    if isinstance(f, dict) and "action_type" in f:
        action_type = f.get("action_type", "")
        if hasattr(action_type, "value"):
            action_type = action_type.value
        action_params = f.get("action_params", {})
        if hasattr(action_params, "model_dump"):
            action_params = action_params.model_dump()
        reasoning = f.get("reasoning", "")
        try:
            final_action = FinalAction(
                action_type=str(action_type),
                action_params=action_params if isinstance(action_params, dict) else {},
                reasoning=str(reasoning),
            )
        except Exception:
            final_action = None

    preferred_language: Optional[str] = (
        context.preferred_language if context is not None else None
    )

    return Thought(
        thought_id=str(row["thought_id"]),
        source_task_id=str(row["source_task_id"]),
        agent_occurrence_id=agent_occurrence_id,
        channel_id=row.get("channel_id"),
        thought_type=thought_type,
        status=status,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        round_number=int(row.get("round_number", 0)),
        content=str(row["content"]),
        context=context,
        thought_depth=int(row.get("thought_depth", 0)),
        ponder_notes=ponder_notes,
        parent_thought_id=row.get("parent_thought_id"),
        final_action=final_action,
        preferred_language=preferred_language,
    )


def _list_with_filter(
    filter_dict: Dict[str, Any],
    *,
    limit: Optional[int] = None,
) -> List[Thought]:
    """Paginate `thought_list`. Returns Thought objects DESC by created_at.

    Persist returns DESC by recorded_at. Caller is responsible for any
    re-sort needed.
    """
    engine = _get_engine()
    last_ts = "9999-12-31T23:59:59Z"
    last_id = ""
    page_size = 200 if limit is None else min(200, max(limit, 1))
    collected: List[Thought] = []

    while True:
        cursor_json = json.dumps(
            {"version": "v1", "last_ts": last_ts, "last_id": last_id}
        )
        raw = engine.thought_list(json.dumps(filter_dict), cursor_json, page_size)
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
            try:
                collected.append(_persist_row_to_thought(row))
            except Exception as e:
                logger.warning(
                    "Failed to materialize persist thought row %s: %s",
                    row.get("thought_id"),
                    e,
                )
            last_ts = str(row.get("created_at", last_ts))
            last_id = str(row.get("thought_id", ""))
            if limit is not None and len(collected) >= limit:
                return collected
        if len(items) < page_size:
            break
    return collected


# ---------------------------------------------------------------------------
# Public API — signatures preserved verbatim from the legacy raw-sqlite3 impl.
# ---------------------------------------------------------------------------


def transfer_thought_ownership(
    thought_id: str,
    from_occurrence_id: str,
    to_occurrence_id: str,
    time_service: TimeServiceProtocol,
    audit_service: AuditServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Transfer thought ownership from one occurrence to another."""
    success = False
    engine = _get_engine()

    raw = engine.thought_get(thought_id)
    if raw is None:
        logger.warning(
            f"Thought {thought_id} not found with occurrence {from_occurrence_id} for ownership transfer"
        )
    else:
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            logger.warning(f"Thought {thought_id} returned non-dict row")
        elif str(row.get("agent_occurrence_id")) != from_occurrence_id:
            logger.warning(
                f"Thought {thought_id} not found with occurrence {from_occurrence_id} for ownership transfer"
            )
        else:
            try:
                row["agent_occurrence_id"] = to_occurrence_id
                row["updated_at"] = time_service.now_iso()
                thought = _persist_row_to_thought(row)
                engine.thought_upsert(json.dumps(_thought_to_persist_payload(thought)))
                logger.info(
                    f"Transferred ownership of thought {thought_id} from {from_occurrence_id} to {to_occurrence_id}"
                )
                success = True
            except Exception as e:
                logger.exception(f"Failed to transfer thought ownership for {thought_id}: {e}")
                success = False

    audit_event = AuditEventData(
        entity_id=thought_id,
        actor="system",
        outcome="success" if success else "failed",
        severity="info",
        action="thought_ownership_transfer",
        resource="thought",
        metadata={
            "thought_id": thought_id,
            "from_occurrence_id": from_occurrence_id,
            "to_occurrence_id": to_occurrence_id,
            "resource_type": "seed_thought",
        },
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            audit_service.log_event("thought_ownership_transfer", cast(EventPayload, audit_event))
        )
    except RuntimeError:
        logger.debug("No event loop running, audit logging deferred")

    return success


def get_thoughts_by_status(
    status: ThoughtStatus,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Thought]:
    """Returns all thoughts with the given status, ASC by created_at."""
    if not isinstance(status, ThoughtStatus):
        raise TypeError(f"Expected ThoughtStatus enum, got {type(status)}: {status}")

    try:
        thoughts = _list_with_filter(
            {"status": status.value, "agent_occurrence_id": occurrence_id},
            limit=limit,
        )
    except Exception as e:
        logger.exception(
            f"Failed to get thoughts with status {status.value} for occurrence {occurrence_id}: {e}"
        )
        return []

    # Legacy callers expect ASC by created_at; persist gives DESC, so reverse.
    thoughts.sort(key=lambda t: t.created_at)
    if limit is not None and len(thoughts) > limit:
        thoughts = thoughts[:limit]
    return thoughts


def add_thought(thought: Thought, db_path: Optional[str] = None) -> str:
    engine = _get_engine()
    try:
        engine.thought_upsert(json.dumps(_thought_to_persist_payload(thought)))
        logger.info(
            f"Added thought ID {thought.thought_id} (occurrence: {thought.agent_occurrence_id}) to database."
        )
        return thought.thought_id
    except Exception as e:
        logger.exception(f"Failed to add thought {thought.thought_id}: {e}")
        raise


def get_thought_by_id(
    thought_id: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Optional[Thought]:
    engine = _get_engine()
    try:
        raw = engine.thought_get(thought_id)
    except Exception as e:
        logger.exception(f"Failed to get thought {thought_id} for occurrence {occurrence_id}: {e}")
        return None
    if raw is None:
        return None
    row = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(row, dict):
        return None
    if str(row.get("agent_occurrence_id")) != occurrence_id:
        return None
    return _persist_row_to_thought(row)


async def async_get_thought_by_id(
    thought_id: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Optional[Thought]:
    """Asynchronous wrapper for get_thought_by_id using asyncio.to_thread."""
    return await asyncio.to_thread(get_thought_by_id, thought_id, occurrence_id, db_path)


def get_thoughts_by_ids(
    thought_ids: List[str],
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Dict[str, Thought]:
    """Fetch multiple thoughts by their IDs. Returns dict thought_id -> Thought."""
    if not thought_ids:
        return {}

    result: Dict[str, Thought] = {}
    engine = _get_engine()
    for tid in thought_ids:
        try:
            raw = engine.thought_get(tid)
        except Exception as e:
            logger.warning(f"Failed to fetch thought {tid}: {e}")
            continue
        if raw is None:
            continue
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            continue
        if str(row.get("agent_occurrence_id")) != occurrence_id:
            continue
        try:
            thought = _persist_row_to_thought(row)
        except Exception as e:
            logger.warning(f"Failed to materialize thought {tid}: {e}")
            continue
        result[thought.thought_id] = thought
    return result


async def async_get_thoughts_by_ids(
    thought_ids: List[str],
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Dict[str, Thought]:
    """Asynchronous wrapper for get_thoughts_by_ids."""
    return await asyncio.to_thread(get_thoughts_by_ids, thought_ids, occurrence_id, db_path)


async def async_get_thought_status(
    thought_id: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Optional[ThoughtStatus]:
    """Retrieve just the status of a thought asynchronously."""

    def _query() -> Optional[ThoughtStatus]:
        thought = get_thought_by_id(thought_id, occurrence_id, db_path)
        return thought.status if thought else None

    return await asyncio.to_thread(_query)


def get_thoughts_by_task_id(
    task_id: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> List[Thought]:
    """Return all thoughts for a given source_task_id as Thought objects, ASC by created_at."""
    try:
        thoughts = _list_with_filter(
            {"source_task_id": task_id, "agent_occurrence_id": occurrence_id}
        )
    except Exception as e:
        logger.exception(f"Failed to get thoughts for task {task_id} in occurrence {occurrence_id}: {e}")
        return []
    thoughts.sort(key=lambda t: t.created_at)
    return thoughts


def delete_thoughts_by_ids(
    thought_ids: List[str],
    occurrence_id: str = "default",
) -> int:
    """Delete thoughts by a list of IDs. Returns the number deleted.

    Persist 1.5.19 does not expose a `thought_delete` API. Production code
    that hits this path relies on the `task_delete` → thoughts cascade or
    on persist's bulk cleanup. We keep the symbol so legacy imports don't
    crash, log a warning when called with anything to delete, and return
    0. See the upstream CIRISPersist follow-up for `thought_delete`.
    """
    if thought_ids:
        logger.warning(
            "delete_thoughts_by_ids called on %d thoughts for occurrence %s, "
            "but persist 1.5.19 has no thought_delete API. No-op; rely on "
            "cascade via task_delete or upstream `thought_delete` issue.",
            len(thought_ids),
            occurrence_id,
        )
    return 0


def count_thoughts(occurrence_id: str = "default", db_path: Optional[str] = None) -> int:
    """Return the count of thoughts that are PENDING or PROCESSING."""
    try:
        # Persist doesn't have OR filter support in `thought_list`; do two queries.
        pending = _list_with_filter(
            {"status": ThoughtStatus.PENDING.value, "agent_occurrence_id": occurrence_id}
        )
        processing = _list_with_filter(
            {"status": ThoughtStatus.PROCESSING.value, "agent_occurrence_id": occurrence_id}
        )
        return len(pending) + len(processing)
    except Exception as e:
        logger.exception(f"Failed to count PENDING or PROCESSING thoughts for occurrence {occurrence_id}: {e}")
        return 0


def update_thought_status(
    thought_id: str,
    status: ThoughtStatus,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
    final_action: Optional[Any] = None,
) -> bool:
    """Update the status of a thought, and optionally final_action."""
    engine = _get_engine()
    status_val = getattr(status, "value", status)

    # Occurrence-id safety: persist's update_status doesn't filter by
    # occurrence; mirror the legacy WHERE clause via a read+verify first.
    existing = get_thought_by_id(thought_id, occurrence_id, db_path)
    if existing is None:
        logger.warning(
            f"No thought found with id {thought_id} in occurrence {occurrence_id} to update status."
        )
        return False

    final_action_json: Optional[str] = None
    if final_action is not None:
        if hasattr(final_action, "model_dump"):
            action_data = final_action.model_dump()
        elif isinstance(final_action, dict):
            action_data = final_action
        else:
            action_data = {"raw": final_action}

        # Normalize ActionSelectionDMAResult → FinalAction shape.
        if "selected_action" in action_data and "action_type" not in action_data:
            selected = action_data.get("selected_action", "")
            action_type_str = selected.value if hasattr(selected, "value") else str(selected)
            params = action_data.get("action_parameters", {})
            if hasattr(params, "model_dump"):
                params = params.model_dump()
            final_action_json = json.dumps(
                {
                    "action_type": action_type_str,
                    "action_params": params,
                    "reasoning": action_data.get("rationale", action_data.get("reasoning", "")),
                }
            )
        else:
            final_action_json = json.dumps(action_data)

    try:
        engine.thought_update_status(thought_id, status_val, final_action_json)
        logger.info(
            f"Updated thought {thought_id} status to {status_val} in occurrence {occurrence_id}"
        )
        return True
    except Exception as e:
        logger.exception(
            f"Failed to update status for thought {thought_id} in occurrence {occurrence_id}: {e}"
        )
        return False


def get_thoughts_older_than(
    older_than_timestamp: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> List[Thought]:
    """Returns all thoughts with created_at older than the given ISO timestamp, ASC."""
    # Persist's `thought_list` doesn't accept a created_at range filter; we
    # paginate the occurrence's full thought set and apply the date filter
    # in Python. The total volume per-occurrence is bounded by normal
    # cleanup so this is acceptable.
    try:
        all_thoughts = _list_with_filter({"agent_occurrence_id": occurrence_id})
    except Exception as e:
        logger.exception(
            f"Failed to get thoughts older than {older_than_timestamp} for occurrence {occurrence_id}: {e}"
        )
        return []
    filtered = [t for t in all_thoughts if t.created_at < older_than_timestamp]
    filtered.sort(key=lambda t: t.created_at)
    return filtered


def get_recent_thoughts(
    occurrence_id: str = "default",
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[ThoughtSummary]:
    """Get recent thoughts as typed summaries for status reporting."""
    try:
        # Persist returns DESC by created_at — exactly what we want.
        thoughts = _list_with_filter(
            {"agent_occurrence_id": occurrence_id},
            limit=limit,
        )
    except Exception as e:
        logger.exception(f"Failed to get recent thoughts for occurrence {occurrence_id}: {e}")
        return []
    return [
        ThoughtSummary(
            thought_id=t.thought_id,
            thought_type=(
                t.thought_type.value
                if isinstance(t.thought_type, ThoughtType)
                else t.thought_type
            ),
            status=t.status.value if isinstance(t.status, ThoughtStatus) else t.status,
            created_at=t.created_at,
            content=t.content,
            source_task_id=t.source_task_id,
        )
        for t in thoughts
    ]
