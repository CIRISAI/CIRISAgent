"""Graph persistence layer — 2.9.0 absorption into ciris-persist.

Pre-2.9.0 this module was the agent's sqlite-direct CRUD over `graph_nodes`
and `graph_edges`. Post-2.9.0 every function routes through the
`ciris-persist` Engine — agent owns the typing, persist owns the storage.

ServiceInitializer calls `set_persist_engine(engine)` after the post-A0a
migration (CIRISAgent#763 Lane A) wires `cirisgraph_*` with the agent's
existing data. After that, all callers of this module talk to persist
transparently.

`db_path` arguments are accepted for signature compatibility but ignored
— persist's Engine owns its own DSN. Tests that need to redirect storage
construct their own Engine and call `set_persist_engine` directly.

Missing persist API (filed upstream): edge-level deletion is not exposed
on the Engine surface, so `delete_graph_edge` and `delete_edges_for_node`
issue direct SQL against persist's `cirisgraph_edges` table. Once
persist exposes `cirisgraph_delete_edge` / `cirisgraph_delete_edges_for_node`
those two functions become typed-API calls too.
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, List, Optional

from ciris_persist import Engine, NotFound  # type: ignore[import-untyped]

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.services.graph_core import (
    GraphEdge,
    GraphEdgeAttributes,
    GraphNode,
    GraphScope,
    NodeType,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level Engine singleton.
# ---------------------------------------------------------------------------

_engine: Optional[Engine] = None
_engine_dsn: Optional[str] = None


def set_persist_engine(engine: Engine, dsn: Optional[str] = None) -> None:
    """Wire the agent's PersistEngine into the persistence module.

    Called by ServiceInitializer post-A0a on first 2.9.0 boot. After this
    call, every function in this module routes through persist's typed
    API instead of legacy sqlite. The DSN argument is informational —
    used in error messages — and may be `None` for in-memory engines.
    """
    global _engine, _engine_dsn
    _engine = engine
    _engine_dsn = dsn
    logger.info("persist engine wired into persistence.models.graph (dsn=%s)", dsn)


def _get_engine() -> Engine:
    """Return the wired engine; raise if not yet set."""
    if _engine is None:
        raise RuntimeError(
            "persist engine not initialized. Call "
            "`ciris_engine.logic.persistence.models.graph.set_persist_engine(engine)` "
            "before any graph operation (typically via ServiceInitializer)."
        )
    return _engine


def get_persist_engine() -> Optional[Engine]:
    """Public accessor — returns the wired engine, or None if not yet set.

    Services outside the persistence module use this to call persist's
    non-graph APIs (federation directory, audit chain, secrets, etc.).
    Returns None rather than raising so callers can short-circuit
    cleanly before the engine is wired (e.g., during early boot).
    """
    return _engine


# ---------------------------------------------------------------------------
# Scope mapping. Agent's GraphScope enum uses lowercase values ('local',
# 'community', 'identity', 'environment'); persist's `NodeFilter` /
# `GraphScope` enum is UPPERCASE per the CHECK constraint on
# `cirisgraph_nodes.scope`.
# ---------------------------------------------------------------------------

_SCOPE_TO_PERSIST = {
    "local": "LOCAL",
    "community": "COMMUNITY",
    "identity": "IDENTITY",
    "environment": "ENVIRONMENT",
}
_SCOPE_FROM_PERSIST = {v: k for k, v in _SCOPE_TO_PERSIST.items()}


def _to_persist_scope(scope: GraphScope) -> str:
    return _SCOPE_TO_PERSIST[scope.value]


def _from_persist_scope(scope_str: str) -> GraphScope:
    return GraphScope(_SCOPE_FROM_PERSIST[scope_str])


# ---------------------------------------------------------------------------
# JSON helpers.
# ---------------------------------------------------------------------------

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles datetime objects and Pydantic models."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return super().default(obj)


def parse_json_field(value: Any) -> Any:
    """Parse a JSON field that may already be a dict (persist auto-parses)
    or still a JSON string (raw column read)."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return {}


def _ensure_tz(iso_str: Optional[str]) -> Optional[str]:
    """Ensure an ISO datetime string carries a timezone suffix.

    Persist's RFC 3339 decoder rejects naive datetimes (e.g.
    `'2026-05-16T11:34:09.731717'`). When `datetime.now().isoformat()`
    produces a naive string, append `Z` so persist treats it as UTC.
    """
    if not iso_str:
        return iso_str
    if iso_str.endswith("Z"):
        return iso_str
    # Look for ±HH:MM or ±HHMM at the tail
    if len(iso_str) >= 6 and iso_str[-6] in "+-" and iso_str[-3] == ":":
        return iso_str
    if len(iso_str) >= 5 and iso_str[-5] in "+-" and iso_str[-3].isdigit():
        return iso_str
    return iso_str + "Z"


def _attributes_to_payload(attrs: Any) -> Any:
    """Normalize attributes to a JSON-serializable dict for persist's
    `attributes` payload field. Persist json.dumps it once on the way to
    storage; passing a pre-encoded JSON string would double-encode."""
    if attrs is None:
        return {}
    if hasattr(attrs, "model_dump"):
        attrs = attrs.model_dump()
    if isinstance(attrs, dict):
        # Round-trip through DateTimeEncoder to coerce datetimes; result
        # is a plain dict persist can json.dumps once.
        return json.loads(json.dumps(attrs, cls=DateTimeEncoder))
    if isinstance(attrs, str):
        # Caller already serialized — try to parse so persist gets a
        # dict, not a string. Fall back to empty dict on parse failure.
        try:
            return json.loads(attrs)
        except Exception:
            return {}
    return json.loads(json.dumps(attrs, cls=DateTimeEncoder))


def _node_from_persist_json(blob: str) -> GraphNode:
    """Reshape persist's GraphNode JSON response into the agent's
    GraphNode pydantic model."""
    d = json.loads(blob) if isinstance(blob, str) else blob
    attrs_field = d.get("attributes")
    if isinstance(attrs_field, str):
        attrs = json.loads(attrs_field) if attrs_field else {}
    else:
        attrs = attrs_field or {}
    return GraphNode(
        id=d["node_id"],
        type=d["node_type"],
        scope=_from_persist_scope(d["scope"]),
        attributes=attrs,
        version=d.get("version", 1),
        updated_by=d.get("updated_by", "system"),
        updated_at=d.get("updated_at"),
    )


def _edge_from_persist_json(blob: Any, fallback_scope: Optional[GraphScope] = None) -> GraphEdge:
    """Reshape persist's GraphEdge JSON response into the agent's
    GraphEdge pydantic model."""
    d = json.loads(blob) if isinstance(blob, str) else blob
    attrs_field = d.get("attributes")
    if isinstance(attrs_field, str):
        attrs = json.loads(attrs_field) if attrs_field else {}
    else:
        attrs = attrs_field or {}
    valid_attrs = {k: attrs[k] for k in ("created_at", "context") if k in attrs}
    scope_str = d.get("scope")
    scope = _from_persist_scope(scope_str) if scope_str else (fallback_scope or GraphScope.LOCAL)
    return GraphEdge(
        source=d["source_node_id"],
        target=d["target_node_id"],
        relationship=d["relationship"],
        scope=scope,
        weight=d.get("weight"),
        attributes=GraphEdgeAttributes(**valid_attrs) if valid_attrs else GraphEdgeAttributes(),
    )


# ---------------------------------------------------------------------------
# Node CRUD.
# ---------------------------------------------------------------------------

def add_graph_node(
    node: GraphNode,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> str:
    """Insert or update a graph node, merging attributes if it exists.

    Goes through `engine.cirisgraph_upsert_node`. Optimistic concurrency
    via `expected_version` — if the row exists we pass its current
    version; otherwise 0.

    Preserves the legacy USER-node side effect: when a new USER node is
    inserted, a 14-day TEMPORARY consent node is created (recursively
    through this same function).
    """
    engine = _get_engine()
    scope_str = _to_persist_scope(node.scope)

    # Lazy wall-clock: persist's decoder requires non-null updated_at /
    # created_at, but only ask time_service.now() if we actually need it
    # AND it returns something usable. Tests sometimes pass AsyncMock
    # time_services whose .now() returns a coroutine that breaks
    # .isoformat() — fall back to datetime.utcnow() in that case.
    def _wall_clock_iso() -> str:
        if time_service is not None:
            try:
                v = time_service.now()
                if hasattr(v, "isoformat"):
                    return str(v.isoformat())
            except Exception:
                pass
        return datetime.utcnow().isoformat() + "Z"

    new_attrs_dict: Any
    if hasattr(node.attributes, "model_dump"):
        new_attrs_dict = node.attributes.model_dump()
    elif isinstance(node.attributes, dict):
        new_attrs_dict = node.attributes
    else:
        new_attrs_dict = {}

    # Optimistic concurrency: read-then-upsert. Merge attributes when the
    # row exists so existing keys aren't lost (matches legacy semantics).
    # Persist returns None (not raise NotFound) when the row is missing.
    expected_version = 0
    existing_node = False
    existing_created_at: Optional[str] = None
    try:
        existing_blob = engine.cirisgraph_get_node(node.id, scope_str)
        if existing_blob is not None:
            existing = json.loads(existing_blob) if isinstance(existing_blob, str) else existing_blob
            existing_node = True
            expected_version = existing.get("version", 0)
            existing_created_at = existing.get("created_at")
            existing_attrs_field = existing.get("attributes")
            if isinstance(existing_attrs_field, str):
                existing_attrs = json.loads(existing_attrs_field) if existing_attrs_field else {}
            else:
                existing_attrs = existing_attrs_field or {}
            if isinstance(existing_attrs, dict) and isinstance(new_attrs_dict, dict):
                new_attrs_dict = {**existing_attrs, **new_attrs_dict}
    except NotFound:
        existing_node = False
    except Exception:
        logger.exception("read-before-upsert failed for node %s/%s", node.id, node.scope.value)
        existing_node = False

    if isinstance(node.updated_at, str):
        updated_at_str = node.updated_at
    elif node.updated_at is not None:
        updated_at_str = node.updated_at.isoformat()
    else:
        updated_at_str = _wall_clock_iso()

    # Pass attributes as a dict — persist json.dumps it once when
    # storing. Passing a pre-encoded JSON string double-encodes
    # (column ends up containing '"{\\"key\\":...}"' instead of '{"key":...}').
    # Round-trip through DateTimeEncoder + json.loads coerces datetime
    # values to ISO strings while keeping the outer shape as a dict.
    attrs_for_payload = json.loads(json.dumps(new_attrs_dict, cls=DateTimeEncoder))

    payload = {
        "node_id": node.id,
        "scope": scope_str,
        "node_type": node.type.value,
        "attributes": attrs_for_payload,
        "version": (expected_version + 1) if existing_node else (node.version or 1),
        "updated_by": node.updated_by or "system",
        # Both updated_at and created_at must be RFC 3339 (tz-aware);
        # _ensure_tz appends 'Z' if the caller's isoformat was naive.
        "updated_at": _ensure_tz(updated_at_str),
        # Required by persist's GraphNode decoder. On update we preserve
        # the existing created_at; on insert we stamp now. Persist may
        # override with its own now() anyway (see CIRISPersist#49).
        "created_at": _ensure_tz(existing_created_at if existing_node else _wall_clock_iso()),
    }

    try:
        engine.cirisgraph_upsert_node(json.dumps(payload), expected_version)
    except Exception:
        logger.exception("Failed to upsert graph node %s/%s", node.id, node.scope.value)
        raise

    # Legacy side effect: new USER nodes trigger 14-day TEMPORARY consent.
    # Preserved verbatim from pre-2.9.0 — see CIRISAgent#756 consent matrix.
    if not existing_node and node.type == NodeType.USER:
        logger.info("New USER node created: %s — creating TEMPORARY consent.", node.id)
        try:
            from ciris_engine.schemas.consent.core import ConsentStream

            consent_node = GraphNode(
                id=f"consent_{node.id}",
                type=NodeType.CONSENT,
                scope=GraphScope.LOCAL,
                attributes={
                    "user_id": node.id,
                    "stream": ConsentStream.TEMPORARY.value,
                    "granted_at": time_service.now().isoformat(),
                    "expires_at": (time_service.now() + timedelta(days=14)).isoformat(),
                    "reason": "Default TEMPORARY consent on user creation",
                    "categories": [],
                    "impact_score": 0.0,
                    "attribution_count": 0,
                },
                updated_by="system_user_creation",
                updated_at=time_service.now(),
            )
            add_graph_node(consent_node, time_service=time_service)
            logger.info("Created TEMPORARY consent for new user %s", node.id)
        except Exception as e:
            logger.warning("Could not create consent for user %s: %s", node.id, e)

    return node.id


def get_graph_node(
    node_id: str,
    scope: GraphScope,
    db_path: Optional[str] = None,
) -> Optional[GraphNode]:
    """Fetch a single graph node by (node_id, scope). None on miss.

    Persist's `cirisgraph_get_node` returns None on miss (not raises) — we
    accept both shapes defensively.
    """
    engine = _get_engine()
    try:
        blob = engine.cirisgraph_get_node(node_id, _to_persist_scope(scope))
        if blob is None:
            return None
        return _node_from_persist_json(blob)
    except NotFound:
        return None
    except Exception:
        logger.exception("get_graph_node failed for %s/%s", node_id, scope.value)
        return None


def delete_graph_node(
    node_id: str,
    scope: GraphScope,
    db_path: Optional[str] = None,
) -> int:
    """Delete a graph node. Returns 1 if deleted, 0 if not found."""
    engine = _get_engine()
    try:
        # hard=True: actually remove the row (vs soft-delete which persist
        # may support for cirislens audit retention — not our concern here).
        engine.cirisgraph_delete_node(node_id, _to_persist_scope(scope), True)
        return 1
    except NotFound:
        return 0
    except Exception:
        logger.exception("delete_graph_node failed for %s/%s", node_id, scope.value)
        return 0


# ---------------------------------------------------------------------------
# Edge CRUD.
# ---------------------------------------------------------------------------

def add_graph_edge(edge: GraphEdge, db_path: Optional[str] = None) -> str:
    """Insert or update a graph edge. Deterministic edge_id:
    `{source}->{target}->{relationship}` (matches legacy semantics)."""
    engine = _get_engine()
    edge_id = f"{edge.source}->{edge.target}->{edge.relationship}"
    # Pull created_at from attributes if the caller provided one (legacy
    # GraphEdgeAttributes uses created_at); otherwise stamp now. Persist
    # may override (see CIRISPersist#49) but the field is required by
    # the decoder either way.
    attrs_obj = edge.attributes
    created_at: Optional[str] = None
    if attrs_obj is not None:
        if hasattr(attrs_obj, "created_at"):
            ca = getattr(attrs_obj, "created_at", None)
            if ca is not None:
                created_at = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
        elif isinstance(attrs_obj, dict):
            ca = attrs_obj.get("created_at")
            if ca is not None:
                created_at = ca.isoformat() if hasattr(ca, "isoformat") else str(ca)
    if created_at is None:
        created_at = datetime.utcnow().isoformat() + "Z"

    payload = {
        "edge_id": edge_id,
        "source_node_id": edge.source,
        "target_node_id": edge.target,
        "scope": _to_persist_scope(edge.scope),
        "relationship": edge.relationship,
        "weight": edge.weight,
        "attributes": _attributes_to_payload(edge.attributes),
        "created_at": _ensure_tz(created_at),
    }
    try:
        engine.cirisgraph_upsert_edge(json.dumps(payload))
    except Exception:
        logger.exception("Failed to upsert graph edge %s", edge_id)
        raise
    return edge_id


def _engine_db_path() -> Optional[str]:
    """Best-effort extraction of the underlying sqlite file path from the
    engine's DSN. Returns None for postgres or in-memory engines.
    Used only by the two edge-delete fallbacks below.

    SQLAlchemy-style DSN convention:
      - `sqlite:////abs/path.db` → 4 slashes → absolute path `/abs/path.db`
      - `sqlite:///rel/path.db`  → 3 slashes → relative path `rel/path.db`
    """
    if not _engine_dsn:
        return None
    if _engine_dsn.startswith("sqlite:////"):
        return "/" + _engine_dsn[len("sqlite:////"):]
    if _engine_dsn.startswith("sqlite:///"):
        return _engine_dsn[len("sqlite:///"):]
    return None


def delete_graph_edge(edge_id: str, db_path: Optional[str] = None) -> int:
    """Delete an edge by edge_id.

    Persist does not expose a typed `cirisgraph_delete_edge` (upstream
    ask filed). Falls back to direct SQL against persist's own
    `cirisgraph_edges` table — same storage, just bypassing the missing
    API.
    """
    path = _engine_db_path()
    if path is None:
        logger.warning("delete_graph_edge: non-sqlite engine; cannot fall back without typed API")
        return 0
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.execute("DELETE FROM cirisgraph_edges WHERE edge_id = ?", (edge_id,))
            conn.commit()
            return cur.rowcount
    except Exception:
        logger.exception("Failed to delete graph edge %s", edge_id)
        return 0


def delete_edges_for_node(
    node_id: str,
    scope: GraphScope,
    db_path: Optional[str] = None,
) -> int:
    """Delete all edges where this node is source or target.

    Persist does not expose a typed bulk-delete API (upstream ask filed).
    Falls back to direct SQL against persist's own `cirisgraph_edges`.
    """
    path = _engine_db_path()
    if path is None:
        logger.warning("delete_edges_for_node: non-sqlite engine; cannot fall back without typed API")
        return 0
    try:
        with sqlite3.connect(path) as conn:
            cur = conn.execute(
                "DELETE FROM cirisgraph_edges "
                "WHERE scope = ? AND (source_node_id = ? OR target_node_id = ?)",
                (_to_persist_scope(scope), node_id, node_id),
            )
            conn.commit()
            return cur.rowcount
    except Exception:
        logger.exception("Failed to delete edges for node %s", node_id)
        return 0


def get_edges_for_node(
    node_id: str,
    scope: Optional[GraphScope] = None,
    db_path: Optional[str] = None,
) -> List[GraphEdge]:
    """Get edges connected to a node. If scope is None, queries all 4
    scopes and merges — persist requires a scope per call."""
    engine = _get_engine()
    edges: List[GraphEdge] = []
    scopes = [scope] if scope is not None else [
        GraphScope.LOCAL, GraphScope.COMMUNITY, GraphScope.IDENTITY, GraphScope.ENVIRONMENT,
    ]
    for s in scopes:
        try:
            blob = engine.cirisgraph_get_edges_for_node(
                node_id, _to_persist_scope(s), "both", None
            )
            arr = json.loads(blob) if isinstance(blob, str) else blob
            for item in arr or []:
                edges.append(_edge_from_persist_json(item, fallback_scope=s))
        except NotFound:
            continue
        except Exception:
            logger.exception("get_edges_for_node failed for %s/%s", node_id, s.value)
    return edges


def get_edges_for_nodes_batch(
    node_ids: List[str],
    scope: Optional[GraphScope] = None,
    db_path: Optional[str] = None,
) -> List[GraphEdge]:
    """Get edges for multiple nodes, deduplicated by (source, target, relationship).

    Persist doesn't expose a batch edge query, so we iterate
    `cirisgraph_get_edges_for_node` per node_id. Cost is linear in
    len(node_ids); for hot paths this could justify an upstream ask."""
    if not node_ids:
        return []
    seen: set[tuple[str, str, str]] = set()
    out: List[GraphEdge] = []
    for nid in node_ids:
        for e in get_edges_for_node(nid, scope=scope):
            key = (e.source, e.target, e.relationship)
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
    return out


# ---------------------------------------------------------------------------
# Node listing / querying.
# ---------------------------------------------------------------------------

def _query_nodes_paged(
    persist_scope: str,
    node_type: Optional[str],
    limit: int,
) -> List[GraphNode]:
    """Walk persist's cursor-paged node listing until we have `limit`
    rows or exhaust the page chain."""
    engine = _get_engine()
    out: List[GraphNode] = []
    cursor: Optional[str] = None
    remaining = limit
    while remaining > 0:
        filt: dict[str, Any] = {"scope": persist_scope}
        if node_type is not None:
            filt["node_type"] = node_type
        page_size = min(remaining, 100)
        blob = engine.cirisgraph_query_nodes(
            json.dumps(filt),
            json.dumps({"cursor": cursor}) if cursor else None,
            page_size,
        )
        page = json.loads(blob) if isinstance(blob, str) else blob
        items = page.get("items", []) if isinstance(page, dict) else []
        for it in items:
            try:
                out.append(_node_from_persist_json(it))
            except Exception:
                logger.exception("Failed to parse persist node row")
        if not items:
            break
        remaining -= len(items)
        cursor = page.get("next_cursor") if isinstance(page, dict) else None
        if not cursor:
            break
    return out


def get_all_graph_nodes(
    scope: Optional[GraphScope] = None,
    node_type: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[GraphNode]:
    """Return all graph nodes matching the filter.

    Persist requires `scope` on every query (AV-47). When the caller
    passes None, we walk all 4 scopes and merge. `offset` is honored via
    in-Python slicing because persist uses opaque cursors rather than
    integer offsets — callers that rely on heavy offsets should switch
    to cursor pagination directly.
    """
    effective_limit = limit if limit is not None else 1000
    scopes = [scope] if scope is not None else [
        GraphScope.LOCAL, GraphScope.COMMUNITY, GraphScope.IDENTITY, GraphScope.ENVIRONMENT,
    ]
    nodes: List[GraphNode] = []
    for s in scopes:
        try:
            nodes.extend(_query_nodes_paged(_to_persist_scope(s), node_type, effective_limit))
        except Exception:
            logger.exception("get_all_graph_nodes scope-walk failed for %s", s.value)
    if offset:
        nodes = nodes[offset:]
    if limit is not None:
        nodes = nodes[:limit]
    return nodes


def get_nodes_by_type(
    node_type: str,
    scope: Optional[GraphScope] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[GraphNode]:
    """Return all nodes of a given type — thin wrapper over `get_all_graph_nodes`."""
    return get_all_graph_nodes(
        scope=scope, node_type=node_type, limit=limit, offset=offset, db_path=db_path
    )
