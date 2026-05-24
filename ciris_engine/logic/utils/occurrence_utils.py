"""
Utilities for multi-occurrence agent coordination.

Provides occurrence discovery and metadata helpers for distributed runtime coordination.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List

logger = logging.getLogger(__name__)


def get_occurrence_count() -> int:
    """Get the total number of agent occurrences.

    Checks environment variables first, falls back to database discovery.

    Returns:
        Number of occurrences (minimum 1)
    """
    # Primary strategy: Environment variable (most reliable)
    env_count = os.getenv("AGENT_OCCURRENCE_COUNT")
    if env_count:
        try:
            count = int(env_count)
            if count > 0:
                logger.debug(f"Occurrence count from environment: {count}")
                return count
        except ValueError:
            logger.warning(f"Invalid AGENT_OCCURRENCE_COUNT value: {env_count}")

    # Fallback strategy: Database discovery (count unique occurrence IDs with recent activity)
    try:
        discovered = discover_active_occurrences(within_minutes=30)
        count = len(discovered)
        if count > 0:
            logger.debug(f"Discovered {count} active occurrences from database activity")
            return count
    except Exception as e:
        logger.warning(f"Failed to discover occurrences from database: {e}")

    # Default: Single occurrence
    logger.debug("No occurrence count found, defaulting to 1")
    return 1


def discover_active_occurrences(within_minutes: int = 10) -> List[str]:
    """Discover active occurrences based on recent database activity.

    Routes through persist's task substrate (`get_all_tasks`) instead of raw
    SQL — persist owns the connection pool; the persist Engine is pinned by
    `initialize_database`.

    Args:
        within_minutes: Only consider occurrences active within this window (default: 10)

    Returns:
        List of unique occurrence IDs with recent activity, sorted alphabetically
    """
    from ciris_engine.logic.persistence.models.tasks import get_all_tasks

    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    cutoff_iso = cutoff_time.isoformat()

    try:
        # `get_all_tasks` with default occurrence returns only that occurrence,
        # so we paginate the full set across __shared__ + per-occurrence rows
        # via a wide list. Persist returns DESC by created_at; for activity
        # discovery we just need DISTINCT agent_occurrence_id within window.
        # The current task substrate doesn't expose a cross-occurrence list;
        # use the existing graph engine's task_list with a wide filter.
        from ciris_engine.logic.persistence.models.graph import get_persist_engine
        import json

        engine = get_persist_engine()
        if engine is None:
            return []

        occurrence_ids: set[str] = set()
        cursor_json = json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
        last_ts = "9999-12-31T23:59:59Z"
        last_id = ""
        while True:
            cur = json.dumps({"version": "v1", "last_ts": last_ts, "last_id": last_id})
            raw = engine.task_list("{}", cur, 500)
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            items = (parsed.get("items") if isinstance(parsed, dict) else None) or []
            if not items:
                break
            for row in items:
                if not isinstance(row, dict):
                    continue
                updated = str(row.get("updated_at", ""))
                if updated < cutoff_iso:
                    # Once we hit a row older than cutoff, persist's DESC ordering
                    # means everything after is also older — short-circuit.
                    return sorted(occurrence_ids)
                occ = row.get("agent_occurrence_id")
                if occ and occ != "__shared__":
                    occurrence_ids.add(str(occ))
                last_ts = updated
                last_id = str(row.get("task_id", ""))
            if len(items) < 500:
                break
        result = sorted(occurrence_ids)
        logger.debug(f"Discovered {len(result)} active occurrences: {result}")
        return result
    except Exception as e:
        logger.exception(f"Failed to discover active occurrences: {e}")
        return []


def get_current_occurrence_id() -> str:
    """Get the current occurrence ID from environment or default.

    Returns:
        Occurrence ID string (default: "default")
    """
    return os.getenv("AGENT_OCCURRENCE_ID", "default")


def is_multi_occurrence_deployment() -> bool:
    """Check if this is a multi-occurrence deployment.

    Returns:
        True if running with multiple occurrences, False if single occurrence
    """
    count = get_occurrence_count()
    return count > 1


def get_occurrence_info() -> dict[str, object]:
    """Get comprehensive occurrence information for diagnostics.

    Returns:
        Dict with occurrence metadata
    """
    occurrence_id = get_current_occurrence_id()
    occurrence_count = get_occurrence_count()
    is_multi = is_multi_occurrence_deployment()

    # Try to get discovered occurrences for additional context
    discovered = []
    try:
        discovered = discover_active_occurrences(within_minutes=30)
    except Exception as e:
        logger.debug(f"Could not discover occurrences for info: {e}")

    return {
        "occurrence_id": occurrence_id,
        "occurrence_count": occurrence_count,
        "is_multi_occurrence": is_multi,
        "discovered_occurrences": discovered,
        "discovery_source": "environment" if os.getenv("AGENT_OCCURRENCE_COUNT") else "database",
    }
