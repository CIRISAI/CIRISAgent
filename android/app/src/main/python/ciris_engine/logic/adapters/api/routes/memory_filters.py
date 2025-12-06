"""
Memory query filters for role-based access control.

Provides double-protection filtering for OBSERVER users:
1. Database-level: Inject SQL filters before query execution
2. Result-level: Filter returned nodes based on user attribution

This ensures OBSERVER users only see memories they created or participated in.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set

from ciris_engine.logic.utils.jsondict_helpers import get_list
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


async def get_user_allowed_ids(auth_service: Any, user_id: str) -> Set[str]:
    """
    Get set of user IDs user is allowed to see (user_id + OAuth links).

    Matches the same logic as reasoning event stream filtering for consistency.

    Args:
        auth_service: Authentication service instance
        user_id: Primary user ID

    Returns:
        Set of allowed user IDs (primary + OAuth linked accounts)
    """
    allowed_ids = {user_id}

    try:
        from ciris_engine.logic.persistence.db import get_db_connection

        # Use db_path with get_db_connection() for proper SQLite/PostgreSQL support
        # CRITICAL: auth_service.db_path may be a PostgreSQL URL, not a file path!
        # sqlite3.connect() cannot handle PostgreSQL URLs, causing "unable to open database file"
        db_path = auth_service.db_path
        query = """
            SELECT oauth_provider, oauth_external_id
            FROM wa_cert
            WHERE wa_id = ? AND oauth_provider IS NOT NULL AND oauth_external_id IS NOT NULL AND active = 1
        """
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
            cursor.close()

            for row in rows:
                # Handle both tuple and dict rows (PostgreSQL uses RealDictCursor)
                if isinstance(row, dict):
                    oauth_provider = row["oauth_provider"]
                    oauth_external_id = row["oauth_external_id"]
                else:
                    oauth_provider, oauth_external_id = row

                # Add both provider:id and bare id format
                allowed_ids.add(f"{oauth_provider}:{oauth_external_id}")
                allowed_ids.add(oauth_external_id)
    except Exception as e:
        logger.error(
            f"Error fetching OAuth links for user {user_id} from database {getattr(auth_service, 'db_path', 'unknown')}: {e}",
            exc_info=True,
        )

    return allowed_ids


def build_user_filter_sql(allowed_user_ids: Set[str]) -> tuple[str, List[str]]:
    """
    Build SQL filter clause for user-based filtering (Defense Layer 1).

    Filters on JSON-extracted attributes.created_by field.

    Args:
        allowed_user_ids: Set of user IDs to allow

    Returns:
        Tuple of (WHERE clause fragment, query parameters)
    """
    if not allowed_user_ids:
        # No allowed users = block everything
        return ("AND 1 = 0", [])

    # Build parameterized query for JSON extraction
    # SQLite: json_extract(attributes_json, '$.created_by')
    placeholders = ",".join("?" * len(allowed_user_ids))
    where_clause = f"AND json_extract(attributes_json, '$.created_by') IN ({placeholders})"
    params = list(allowed_user_ids)

    return (where_clause, params)


def _extract_attributes_dict(node: GraphNode) -> Optional[JSONDict]:
    """
    Extract attributes as a dictionary from a GraphNode.

    Args:
        node: GraphNode to extract attributes from

    Returns:
        Dictionary of attributes, or None if extraction fails
    """
    attrs = node.attributes
    if isinstance(attrs, dict):
        return attrs
    elif hasattr(attrs, "model_dump"):
        return attrs.model_dump()
    elif hasattr(attrs, "dict"):
        return attrs.dict()
    else:
        logger.warning(f"Cannot inspect attributes for node {node.id}, skipping")
        return None


def _check_created_by(attrs_dict: JSONDict, allowed_user_ids: Set[str]) -> bool:
    """Check if node creator is in allowed users."""
    created_by = attrs_dict.get("created_by")
    return bool(created_by and created_by in allowed_user_ids)


def _check_user_list(attrs_dict: JSONDict, allowed_user_ids: Set[str]) -> bool:
    """Check if any user in user_list is allowed."""
    user_list = get_list(attrs_dict, "user_list", [])
    return any(uid in allowed_user_ids for uid in user_list if isinstance(uid, str))


def _check_task_summaries(attrs_dict: JSONDict, allowed_user_ids: Set[str]) -> bool:
    """Check if any task summary user_id is allowed."""
    task_summaries = attrs_dict.get("task_summaries", {})
    if not isinstance(task_summaries, dict):
        return False

    for task_data in task_summaries.values():
        if isinstance(task_data, dict):
            task_user_id = task_data.get("user_id")
            if task_user_id and task_user_id in allowed_user_ids:
                return True
    return False


def _check_conversations(attrs_dict: JSONDict, allowed_user_ids: Set[str]) -> bool:
    """Check if any conversation author_id is allowed."""
    conversations = attrs_dict.get("conversations_by_channel", {})
    if not isinstance(conversations, dict):
        return False

    for channel_messages in conversations.values():
        if isinstance(channel_messages, list):
            for msg in channel_messages:
                if isinstance(msg, dict):
                    author_id = msg.get("author_id")
                    if author_id and author_id in allowed_user_ids:
                        return True
    return False


def _node_matches_user_attribution(node: GraphNode, allowed_user_ids: Set[str]) -> bool:
    """
    Check if a single node matches user attribution criteria.

    Args:
        node: GraphNode to check
        allowed_user_ids: Set of allowed user IDs

    Returns:
        True if node should be included, False otherwise
    """
    attrs_dict = _extract_attributes_dict(node)
    if attrs_dict is None:
        return False

    # Check all attribution pathways (order by frequency for performance)
    return (
        _check_created_by(attrs_dict, allowed_user_ids)
        or _check_user_list(attrs_dict, allowed_user_ids)
        or _check_task_summaries(attrs_dict, allowed_user_ids)
        or _check_conversations(attrs_dict, allowed_user_ids)
    )


def filter_nodes_by_user_attribution(nodes: List[GraphNode], allowed_user_ids: Set[str]) -> List[GraphNode]:
    """
    Filter graph nodes by user attribution (Defense Layer 2).

    Checks multiple attribution fields for comprehensive coverage:
    - attributes.created_by (direct creator)
    - attributes.user_list[] (participants in consolidated nodes)
    - attributes.conversations_by_channel[*][].author_id (conversation participants)
    - attributes.task_summaries[*].user_id (task creators)

    Args:
        nodes: List of GraphNode objects to filter
        allowed_user_ids: Set of user IDs to allow

    Returns:
        Filtered list of GraphNode objects
    """
    if not allowed_user_ids:
        return []

    filtered = [node for node in nodes if _node_matches_user_attribution(node, allowed_user_ids)]

    logger.debug(
        f"Filtered {len(nodes)} nodes to {len(filtered)} for user access control "
        f"(allowed_ids: {len(allowed_user_ids)})"
    )

    return filtered


def should_apply_user_filtering(user_role: UserRole) -> bool:
    """
    Determine if user filtering should be applied based on role.

    Args:
        user_role: User's role

    Returns:
        True if filtering should be applied (OBSERVER), False for ADMIN+
    """
    # ADMIN and higher roles bypass filtering
    return not user_role.has_permission(UserRole.ADMIN)
