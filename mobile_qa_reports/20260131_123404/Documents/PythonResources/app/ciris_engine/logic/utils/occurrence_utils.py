"""
Utilities for multi-occurrence agent coordination.

Provides occurrence discovery and metadata helpers for distributed runtime coordination.
"""

import logging
import os
import sqlite3
from typing import Any, List, Optional, Union

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.core import RetryConnection

logger = logging.getLogger(__name__)


def get_occurrence_count(db_path: Optional[str] = None) -> int:
    """Get the total number of agent occurrences.

    Checks environment variables first, falls back to database discovery.

    Args:
        db_path: Optional database path for testing

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
        discovered = discover_active_occurrences(within_minutes=30, db_path=db_path)
        count = len(discovered)
        if count > 0:
            logger.debug(f"Discovered {count} active occurrences from database activity")
            return count
    except Exception as e:
        logger.warning(f"Failed to discover occurrences from database: {e}")

    # Default: Single occurrence
    logger.debug("No occurrence count found, defaulting to 1")
    return 1


def discover_active_occurrences(within_minutes: int = 10, db_path: Optional[str] = None) -> List[str]:
    """Discover active occurrences based on recent database activity.

    Args:
        within_minutes: Only consider occurrences active within this window (default: 10)
        db_path: Optional database path

    Returns:
        List of unique occurrence IDs with recent activity, sorted alphabetically
    """
    import sqlite3
    from datetime import datetime, timedelta, timezone

    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=within_minutes)
    cutoff_iso = cutoff_time.isoformat()

    sql = """
        SELECT DISTINCT agent_occurrence_id
        FROM tasks
        WHERE agent_occurrence_id != '__shared__'
          AND updated_at > ?
        ORDER BY agent_occurrence_id
    """

    try:
        # If explicit db_path provided, connect directly (for testing)
        if db_path:
            test_conn = sqlite3.connect(db_path)
            test_conn.row_factory = sqlite3.Row
            try:
                cursor = test_conn.cursor()
                cursor.execute(sql, (cutoff_iso,))
                rows = cursor.fetchall()
                occurrence_ids = [row["agent_occurrence_id"] for row in rows]
                logger.debug(f"Discovered {len(occurrence_ids)} active occurrences: {occurrence_ids}")
                return occurrence_ids
            finally:
                test_conn.close()
        else:
            # Use get_db_connection for production (uses config service)
            prod_conn: Union[sqlite3.Connection, RetryConnection, Any] = get_db_connection()
            try:
                cursor = prod_conn.cursor()
                cursor.execute(sql, (cutoff_iso,))
                rows = cursor.fetchall()
                occurrence_ids = [row["agent_occurrence_id"] for row in rows]
                logger.debug(f"Discovered {len(occurrence_ids)} active occurrences: {occurrence_ids}")
                return occurrence_ids
            finally:
                prod_conn.close()
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


def get_occurrence_info(db_path: Optional[str] = None) -> dict[str, object]:
    """Get comprehensive occurrence information for diagnostics.

    Args:
        db_path: Optional database path for testing

    Returns:
        Dict with occurrence metadata
    """
    occurrence_id = get_current_occurrence_id()
    occurrence_count = get_occurrence_count(db_path=db_path)
    is_multi = is_multi_occurrence_deployment()

    # Try to get discovered occurrences for additional context
    discovered = []
    try:
        discovered = discover_active_occurrences(within_minutes=30, db_path=db_path)
    except Exception as e:
        logger.debug(f"Could not discover occurrences for info: {e}")

    return {
        "occurrence_id": occurrence_id,
        "occurrence_count": occurrence_count,
        "is_multi_occurrence": is_multi,
        "discovered_occurrences": discovered,
        "discovery_source": "environment" if os.getenv("AGENT_OCCURRENCE_COUNT") else "database",
    }
