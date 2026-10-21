"""WORKED EXAMPLE — thoughts.py rewrite to persist substrates.

This is a reference implementation showing the migration pattern.
Apply the same shape (helper functions + per-public-function rewrite +
public signatures preserved) to every other legacy table.

NOTE: this file is NOT imported anywhere. It's a reference scaffold for
the T-lane migration agents. The real file at
ciris_engine/logic/persistence/models/thoughts.py is replaced wholesale
when the TasksChain agent finishes its work (tasks + thoughts +
scheduled_tasks together because of FK constraints).

The pattern:
  1. _get_engine() — fetch the wired persist Engine; raise cleanly if unset
  2. _<entity>_to_persist_payload(model) — agent pydantic → persist dict
  3. _persist_row_to_<entity>(row) — persist dict → agent pydantic
  4. _list_with_filter(filter_dict, *, limit=None) — paginated reader
  5. Public functions preserved verbatim in signature, internals swapped
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
    """Convert a Thought into the dict shape `engine.thought_upsert` accepts.

    Persist takes `context`/`ponder_notes`/`final_action` as nested
    dicts/lists; it json.dumps them onto the SQL side itself.
    """
    thought_dict = thought.model_dump(mode="json")
    payload: Dict[str, Any] = {
        "thought_id": thought.thought_id,
        "source_task_id": thought.source_task_id,
        "agent_occurrence_id": thought.agent_occurrence_id,
        "channel_id": thought.channel_id,
        "thought_type": thought.thought_type.value
        if isinstance(thought.thought_type, ThoughtType)
        else thought.thought_type,
        "status": thought.status.value
        if isinstance(thought.status, ThoughtStatus)
        else thought.status,
        "created_at": thought.created_at,
        "updated_at": thought.updated_at,
        "round_number": thought.round_number,
        "content": thought.content,
        "thought_depth": thought.thought_depth,
        "parent_thought_id": thought.parent_thought_id,
    }
    ctx = thought_dict.get("context")
    if ctx is not None:
        payload["context"] = ctx
    pn = thought_dict.get("ponder_notes")
    if pn is not None:
        payload["ponder_notes"] = pn
    fa = thought_dict.get("final_action")
    if fa is not None:
        payload["final_action"] = fa
    return payload


def _persist_row_to_thought(row: Dict[str, Any]) -> Thought:
    """Materialize a persist thought row into a Thought.

    Persist returns context/ponder_notes/final_action as parsed dicts/lists
    (not their _json SQL-column counterparts).
    """
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
            context = ThoughtContext(
                task_id=task_id,
                channel_id=ctx_data.get("channel_id"),
                round_number=ctx_data.get("round_number", 0),
                depth=ctx_data.get("depth", 0),
                parent_thought_id=ctx_data.get("parent_thought_id"),
                correlation_id=correlation_id,
                agent_occurrence_id=ctx_data.get("agent_occurrence_id", agent_occurrence_id),
                preferred_language=ctx_data.get("preferred_language"),
            )

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
    if isinstance(f, dict) and f:
        action_type = f.get("action_type") or f.get("selected_action") or ""
        if hasattr(action_type, "value"):
            action_type = action_type.value
        action_params = f.get("action_params") or f.get("action_parameters") or {}
        if hasattr(action_params, "model_dump"):
            action_params = action_params.model_dump()
        reasoning = f.get("reasoning") or f.get("rationale") or ""
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
    """Paginate `thought_list`. Returns Thought objects DESC by created_at."""
    engine = _get_engine()
    last_ts = "9999-12-31T23:59:59Z"
    last_id = ""
    page_size = 200 if limit is None else min(200, limit)
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
            collected.append(_persist_row_to_thought(row))
            last_ts = str(row.get("created_at", last_ts))
            last_id = str(row.get("thought_id", ""))
            if limit is not None and len(collected) >= limit:
                return collected
        if len(items) < page_size:
            break
    return collected


# ---------------------------------------------------------------------------
# Public API (signatures preserved for backward compat with all callers).
# Showing the rewrite pattern; apply the same to every legacy table.
# ---------------------------------------------------------------------------


def add_thought(thought: Thought, db_path: Optional[str] = None) -> str:
    engine = _get_engine()
    engine.thought_upsert(json.dumps(_thought_to_persist_payload(thought)))
    logger.info(
        f"Added thought ID {thought.thought_id} "
        f"(occurrence: {thought.agent_occurrence_id}) to database."
    )
    return thought.thought_id


def get_thought_by_id(
    thought_id: str,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
) -> Optional[Thought]:
    engine = _get_engine()
    raw = engine.thought_get(thought_id)
    if raw is None:
        return None
    row = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(row, dict):
        return None
    if str(row.get("agent_occurrence_id")) != occurrence_id:
        return None
    return _persist_row_to_thought(row)


def update_thought_status(
    thought_id: str,
    status: ThoughtStatus,
    occurrence_id: str = "default",
    db_path: Optional[str] = None,
    final_action: Optional[Any] = None,
) -> bool:
    engine = _get_engine()
    status_val = getattr(status, "value", status)

    # Occurrence-id safety: persist's update_status doesn't filter by
    # occurrence; mirror the legacy WHERE clause via a read+verify first.
    existing = get_thought_by_id(thought_id, occurrence_id, db_path)
    if existing is None:
        logger.warning(
            f"No thought found with id {thought_id} in occurrence "
            f"{occurrence_id} to update status."
        )
        return False

    final_action_json: Optional[str] = None
    if final_action is not None:
        # Normalize ActionSelectionDMAResult → FinalAction
        if hasattr(final_action, "model_dump"):
            action_data = final_action.model_dump()
        elif isinstance(final_action, dict):
            action_data = final_action
        else:
            action_data = {"raw": final_action}
        if "selected_action" in action_data and "action_type" not in action_data:
            selected = action_data.get("selected_action", "")
            action_type_str = (
                selected.value if hasattr(selected, "value") else str(selected)
            )
            params = action_data.get("action_parameters", {})
            if hasattr(params, "model_dump"):
                params = params.model_dump()
            final_action_json = json.dumps(
                {
                    "action_type": action_type_str,
                    "action_params": params,
                    "reasoning": action_data.get(
                        "rationale", action_data.get("reasoning", "")
                    ),
                }
            )
        else:
            final_action_json = json.dumps(action_data)

    engine.thought_update_status(thought_id, status_val, final_action_json)
    return True


# transfer_thought_ownership, get_thoughts_by_status, get_thoughts_by_ids,
# async_get_*, get_thoughts_by_task_id, get_thoughts_older_than, count_thoughts,
# get_recent_thoughts, delete_thoughts_by_ids — all follow the same pattern.
# See the full rewrite in conversation history or
# the MIGRATION_BIBLE.md for the full function list.
