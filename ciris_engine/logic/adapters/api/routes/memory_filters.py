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

from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.services.graph_core import GraphNode

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
        db = auth_service.db_manager
        query = """
            SELECT oauth_provider, oauth_external_id
            FROM wa_cert
            WHERE user_id = ? AND oauth_provider IS NOT NULL AND oauth_external_id IS NOT NULL
        """
        async with db.connection() as conn:
            rows = await conn.execute_fetchall(query, (user_id,))
            for row in rows:
                oauth_provider, oauth_external_id = row
                # Add both provider:id and bare id format
                allowed_ids.add(f"{oauth_provider}:{oauth_external_id}")
                allowed_ids.add(oauth_external_id)
    except Exception as e:
        logger.error(f"Error fetching OAuth links for user {user_id}: {e}", exc_info=True)

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

    filtered = []

    for node in nodes:
        # Extract attributes
        attrs = node.attributes
        if isinstance(attrs, dict):
            attrs_dict = attrs
        elif hasattr(attrs, "model_dump"):
            attrs_dict = attrs.model_dump()
        elif hasattr(attrs, "dict"):
            attrs_dict = attrs.dict()
        else:
            # Can't inspect attributes - skip for safety
            logger.warning(f"Cannot inspect attributes for node {node.id}, skipping")
            continue

        # Check direct creator (primary field)
        created_by = attrs_dict.get("created_by")
        if created_by and created_by in allowed_user_ids:
            filtered.append(node)
            continue

        # Check user_list (consolidated nodes)
        user_list = attrs_dict.get("user_list", [])
        if any(uid in allowed_user_ids for uid in user_list):
            filtered.append(node)
            continue

        # Check task_summaries (TaskSummaryNode)
        task_summaries = attrs_dict.get("task_summaries", {})
        if isinstance(task_summaries, dict):
            for task_data in task_summaries.values():
                if isinstance(task_data, dict):
                    task_user_id = task_data.get("user_id")
                    if task_user_id and task_user_id in allowed_user_ids:
                        filtered.append(node)
                        break
            else:
                # No match in task summaries, continue checking
                pass
        elif filtered:
            # Already added, skip
            continue

        # Check conversations_by_channel (ConversationSummaryNode)
        conversations = attrs_dict.get("conversations_by_channel", {})
        if isinstance(conversations, dict):
            matched = False
            for channel_messages in conversations.values():
                if isinstance(channel_messages, list):
                    for msg in channel_messages:
                        if isinstance(msg, dict):
                            author_id = msg.get("author_id")
                            if author_id and author_id in allowed_user_ids:
                                filtered.append(node)
                                matched = True
                                break
                    if matched:
                        break

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
