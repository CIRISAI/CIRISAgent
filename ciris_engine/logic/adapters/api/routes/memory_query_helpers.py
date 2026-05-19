"""Memory query helpers — persist-substrate routed for 2.9.0 Phase 4.

Phase 4 (CIRISAgent#763, CIRISPersist#65/67): every public query helper
builds a persist `NodeFilter` dict and runs it through
`cirisgraph_query_nodes`. The OBSERVER user filter uses persist's new
`attribute_match` predicate (CIRISPersist#67, v1.6.1) instead of raw
JSON-path SQL.

Following CIRIS principles:
- Single Responsibility: Each class handles one aspect
- Type Safety: All inputs and outputs are typed
- No Exceptions: No special cases or bypass patterns
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


# Substrate constants
_DEFAULT_SCOPE = "LOCAL"
_PAGE_SIZE = 500


class QueryBuilder:
    """Builds persist NodeFilter dicts (no SQL).

    Each `build_*_query` returns:
      (primary_filter, post_query_options)
    where:
      - `primary_filter` is the NodeFilter dict for cirisgraph_query_nodes
      - `post_query_options` carries client-side filters that persist's
        substrate doesn't yet express (free-text `query` string, secondary
        user-filter paths).
    """

    @staticmethod
    def _scope_value(scope: Optional[Any]) -> str:
        """Normalize scope input to persist's uppercase enum string."""
        if scope is None:
            return _DEFAULT_SCOPE
        if hasattr(scope, "value"):
            return str(scope.value).upper()
        return str(scope).upper()

    @staticmethod
    def build_timeline_query(
        start_time: datetime,
        end_time: datetime,
        scope: Optional[Any] = None,
        node_type: Optional[Any] = None,
        exclude_metrics: bool = True,
        limit: int = 100,
        user_filter_ids: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build a timeline query — time-windowed listing with optional filters."""
        node_filter: Dict[str, Any] = {
            "scope": QueryBuilder._scope_value(scope),
            "updated_after": start_time.isoformat(),
            "updated_before": end_time.isoformat(),
        }

        if node_type:
            node_filter["node_type"] = (
                node_type.value if hasattr(node_type, "value") else str(node_type)
            )

        if exclude_metrics:
            # CIRISPersist#65: exclude tsdb_data + metric_% pattern
            node_filter["exclude"] = {
                "node_type": "tsdb_data",
                "node_id_pattern": "metric_%",
            }

        post: Dict[str, Any] = {"limit": limit}
        if user_filter_ids:
            post["user_filter_ids"] = list(user_filter_ids)

        # If a single-path user filter applies, attach it directly so persist
        # does the filtering. Multi-path OR (created_by + user_list + ...) is
        # applied client-side below.
        if user_filter_ids:
            node_filter["attribute_match"] = {
                "path": "created_by",
                "equals_any": list(user_filter_ids),
            }

        return node_filter, post

    @staticmethod
    def build_search_query(
        query: Optional[str] = None,
        node_type: Optional[NodeType] = None,
        scope: Optional[GraphScope] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        user_filter_ids: Optional[List[str]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Build a search query with multiple filters."""
        node_filter: Dict[str, Any] = {"scope": QueryBuilder._scope_value(scope)}

        if node_type:
            node_filter["node_type"] = (
                node_type.value if hasattr(node_type, "value") else str(node_type)
            )
        if since:
            node_filter["updated_after"] = since.isoformat()
        if until:
            node_filter["updated_before"] = until.isoformat()
        if user_filter_ids:
            node_filter["attribute_match"] = {
                "path": "created_by",
                "equals_any": list(user_filter_ids),
            }

        post: Dict[str, Any] = {"limit": limit, "offset": offset}
        if query:
            post["query_substring"] = query
        if tags:
            post["tags"] = list(tags)
        if user_filter_ids:
            post["user_filter_ids"] = list(user_filter_ids)

        return node_filter, post


class AttributeParser:
    """Parses attribute payloads from persist rows.

    Persist returns `attributes` as either a dict (auto-decoded) or a
    JSON string (passthrough). This helper normalizes to a dict.
    """

    @staticmethod
    def parse_attributes(attributes: Any, node_id: str) -> JSONDict:
        if not attributes:
            return {}
        if isinstance(attributes, dict):
            return attributes
        try:
            result = json.loads(attributes) if isinstance(attributes, (bytes, str)) else {}
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Failed to parse attributes for node {node_id}")
            return {}


class DateTimeParser:
    """Parses datetime values from various formats."""

    @staticmethod
    def parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass
            try:
                return datetime.fromisoformat(value.split("+")[0])
            except ValueError:
                pass
        return None


class GraphNodeBuilder:
    """Build GraphNode objects from persist `cirisgraph_query_nodes` rows."""

    @staticmethod
    def build_from_row(row: Any) -> Optional[GraphNode]:
        """Build a GraphNode from a persist row (always a dict in 1.6.x)."""
        try:
            if not isinstance(row, dict):
                return None

            node_id = row["node_id"]
            scope = row.get("scope", _DEFAULT_SCOPE)
            # Persist returns scope uppercase; the agent's GraphScope enum
            # uses lowercase values.
            scope_lower = str(scope).lower()
            node_type = row.get("node_type", "")
            attributes_blob = row.get("attributes")
            version = row.get("version", 1)
            updated_by = row.get("updated_by") or "system"
            updated_at_raw = row.get("updated_at")
            created_at_raw = row.get("created_at")

            attributes_dict = AttributeParser.parse_attributes(attributes_blob, node_id)
            updated_at = DateTimeParser.parse_datetime(updated_at_raw)
            created_at = DateTimeParser.parse_datetime(created_at_raw)

            tags = attributes_dict.pop("tags", [])
            created_by = attributes_dict.pop("created_by", updated_by)

            typed_attributes = GraphNodeAttributes(
                created_at=created_at or updated_at or datetime.now(),
                updated_at=updated_at or datetime.now(),
                created_by=created_by,
                tags=tags if isinstance(tags, list) else [],
            )

            return GraphNode(
                id=node_id,
                scope=scope_lower,
                type=node_type,
                attributes=typed_attributes,
                version=int(version) if version else 1,
                updated_by=updated_by,
                updated_at=updated_at,
            )
        except Exception as e:
            logger.error(f"Failed to build GraphNode from persist row: {e}")
            return None

    @staticmethod
    def build_from_rows(rows: List[Any]) -> List[GraphNode]:
        """Build multiple GraphNodes from persist rows."""
        return [n for n in (GraphNodeBuilder.build_from_row(r) for r in rows) if n is not None]


class DatabaseExecutor:
    """Executes node queries through persist's `cirisgraph_query_nodes`."""

    @staticmethod
    def execute_query(
        db_path: Optional[str],
        node_filter: Dict[str, Any],
        post_options: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Paginate persist nodes matching `node_filter` and apply client-side post-filters.

        The legacy signature (db_path, query, params) is replaced. The
        `db_path` argument is retained for signature compatibility (persist
        owns the connection).

        Client-side post-filters applied after pagination:
        - `query_substring`: free-text LIKE over the JSON-encoded attributes
        - `tags`: each tag must appear in `attributes.tags`
        - `user_filter_ids` (OBSERVER Layer 1, multi-path OR): combined
          via additional persist queries against `user_list` array containment
          + client-side check of nested `author_id` / `task_summaries.user_id`
        """
        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine

            engine = get_persist_engine()
            if engine is None:
                return []

            limit = int(post_options.get("limit", 100))
            offset = int(post_options.get("offset", 0))
            query_substring = post_options.get("query_substring")
            tags = post_options.get("tags") or []
            user_filter_ids = post_options.get("user_filter_ids") or []

            primary_rows = _paginate_nodes(engine, node_filter, limit + offset + len(tags) * 10)

            # OBSERVER multi-path OR: when a user filter is set, also pull
            # rows where `user_list` contains any allowed id, then union by
            # node_id with the primary `created_by` set.
            if user_filter_ids:
                filter_user_list = dict(node_filter)
                filter_user_list["attribute_match"] = {
                    "path": "user_list",
                    "array_contains_any": list(user_filter_ids),
                }
                secondary_rows = _paginate_nodes(engine, filter_user_list, limit + offset + 100)
                seen_ids = {str(r.get("node_id")) for r in primary_rows}
                for r in secondary_rows:
                    if str(r.get("node_id")) not in seen_ids:
                        primary_rows.append(r)
                        seen_ids.add(str(r.get("node_id")))

            # Client-side substring + tag filter (persist substrate doesn't
            # expose free-text yet).
            filtered = []
            for row in primary_rows:
                attrs_blob = row.get("attributes")
                if isinstance(attrs_blob, (dict, list)):
                    attrs_text = json.dumps(attrs_blob)
                else:
                    attrs_text = str(attrs_blob or "")
                if query_substring and query_substring not in attrs_text:
                    continue
                if tags and not all(f'"{t}"' in attrs_text for t in tags):
                    continue
                filtered.append(row)

            if user_filter_ids:
                # Client-side check for nested user attribution paths persist
                # doesn't yet predicate on (task_summaries[].user_id, author_id).
                filtered = [
                    row
                    for row in filtered
                    if _row_matches_user_layer1(row, set(user_filter_ids))
                ]

            return filtered[offset : offset + limit]
        except Exception as e:
            logger.error(f"Persist node query failed: {e}")
            return []

    @staticmethod
    def get_db_path(memory_service: Any) -> Optional[str]:
        """Legacy helper retained for caller signature compat."""
        return getattr(memory_service, "db_path", None)


def _paginate_nodes(engine: Any, node_filter: Dict[str, Any], target: int) -> List[Dict[str, Any]]:
    """Paginate cirisgraph_query_nodes until we have at least `target` rows."""
    out: List[Dict[str, Any]] = []
    cursor = json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
    while len(out) < target:
        raw = engine.cirisgraph_query_nodes(json.dumps(node_filter), cursor, _PAGE_SIZE)
        parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        if not items:
            break
        out.extend(r for r in items if isinstance(r, dict))
        if len(items) < _PAGE_SIZE:
            break
        next_cursor = parsed.get("cursor") if isinstance(parsed, dict) else None
        if not next_cursor:
            break
        cursor = next_cursor if isinstance(next_cursor, str) else json.dumps(next_cursor)
    return out


def _row_matches_user_layer1(row: Dict[str, Any], allowed_user_ids: set[str]) -> bool:
    """Client-side check for OBSERVER user-filter paths persist doesn't predicate on.

    Persist's `attribute_match` covers the primary paths (created_by + user_list)
    via two queries that we union. This helper covers the deeper-nested paths:
    `task_summaries[].user_id` and `conversations[*].author_id`.
    """
    attrs = row.get("attributes") or {}
    if not isinstance(attrs, dict):
        try:
            attrs = json.loads(str(attrs))
        except Exception:
            return True  # Tolerate unparseable rows — fail open per legacy parity
        if not isinstance(attrs, dict):
            return True

    # Primary paths already covered by persist filter — accept if present.
    if str(attrs.get("created_by", "")) in allowed_user_ids:
        return True
    user_list = attrs.get("user_list")
    if isinstance(user_list, list) and any(str(u) in allowed_user_ids for u in user_list):
        return True

    # Nested paths persist doesn't yet predicate.
    task_summaries = attrs.get("task_summaries")
    if isinstance(task_summaries, list):
        for ts in task_summaries:
            if isinstance(ts, dict) and str(ts.get("user_id", "")) in allowed_user_ids:
                return True

    conversations = attrs.get("conversations")
    if isinstance(conversations, dict):
        for thread in conversations.values():
            if isinstance(thread, list):
                for msg in thread:
                    if isinstance(msg, dict) and str(msg.get("author_id", "")) in allowed_user_ids:
                        return True

    return False


class TimeRangeCalculator:
    """Calculates time ranges for queries."""

    @staticmethod
    def calculate_range(hours: int) -> Tuple[datetime, datetime]:
        """Calculate start and end time from hours (UTC)."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)
        return start_time, now

    @staticmethod
    def calculate_range_from_days(days: int) -> Tuple[datetime, datetime]:
        """Calculate start and end time from days (UTC)."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(days=days)
        return start_time, now
