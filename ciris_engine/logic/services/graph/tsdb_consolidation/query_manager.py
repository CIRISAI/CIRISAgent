"""Query management for TSDB consolidation — persist-substrate routed for 2.9.0.

Phase 3b cutover (CIRISAgent#763, CIRISPersist#63 + #68): the legacy
sqlite3-cursor-based QueryManager retired. The agent's TSDB orchestration
calls a small handful of methods on this class for locks + lightweight
period probes; every method now routes through persist's substrate.

Behavior contract preserved:
- `acquire_period_lock` / `release_period_lock` — persist `lock_acquire` /
  `lock_release` on a per-period key.
- `acquire_consolidation_lock` / `release_consolidation_lock` — same, with
  a richer key for extensive/profound tiers.
- `_try_acquire_lock` — internal lock primitive.
- `check_period_consolidated` — wraps `tsdb_query_summary_nodes` and
  returns True when ≥1 summary exists in the window.
- `query_all_nodes_in_period` — paginates persist's `cirisgraph_query_nodes`
  with a time-range filter; returns the per-node_type bucket the legacy
  helpers consumed.
- `get_last_consolidated_period` — DESC walk of tsdb_summary nodes via
  `cirisgraph_query_nodes`.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.schemas.services.graph.query_results import TSDBNodeQueryResult

logger = logging.getLogger(__name__)


_LOCK_TTL_SECS = 60 * 30  # 30 minutes — long enough for a 6h-period consolidation


def _engine() -> Any:
    """Resolve the wired persist engine."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    return get_persist_engine()


def _tenant() -> str:
    return os.environ.get("CIRIS_AGENT_TENANT", "agent-default")


class QueryManager:
    """Thin persist-substrate wrapper preserving the legacy public API."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None, db_path: Optional[str] = None):
        """
        Initialize query manager.

        Args:
            memory_bus: Memory bus for graph operations (retained for signature
                compatibility; reads route through persist now).
            db_path: legacy parameter — persist owns the connection.
        """
        self._memory_bus = memory_bus
        self._db_path = db_path
        self._instance_id = socket.gethostname()

    # ------------------------------------------------------------------
    # Lock primitives — persist `lock_acquire` / `lock_release`
    # ------------------------------------------------------------------

    def _try_acquire_lock(self, lock_key: str, consolidation_type: str, period_identifier: str) -> bool:
        """Attempt to acquire the named lock via persist's lock substrate.

        Returns True if this caller now owns the lock; False if another
        owner holds it (stale locks auto-expire at TTL).
        """
        engine = _engine()
        if engine is None:
            logger.debug("persist engine not wired; lock %s skipped", lock_key)
            return False
        try:
            raw = engine.lock_acquire(lock_key, self._instance_id, _LOCK_TTL_SECS)
        except Exception as e:
            logger.warning("lock_acquire(%s) failed: %s", lock_key, e)
            return False
        parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        if isinstance(parsed, dict):
            # Persist returns {"acquired": bool, ...} or similar envelope shape;
            # fall back to truthy check otherwise.
            for key in ("acquired", "ok", "granted"):
                if key in parsed:
                    return bool(parsed[key])
        return bool(parsed)

    def _release_lock(self, lock_key: str, consolidation_type: str, period_identifier: str) -> None:
        """Release a named lock if this caller still owns it."""
        engine = _engine()
        if engine is None:
            return
        try:
            engine.lock_release(lock_key, self._instance_id)
        except Exception as e:
            logger.warning("lock_release(%s) failed: %s", lock_key, e)

    def acquire_consolidation_lock(self, consolidation_type: str, period_identifier: str) -> bool:
        """Acquire a typed consolidation lock (extensive/profound) for a period."""
        lock_key = f"tsdb:{consolidation_type}:{period_identifier}"
        return self._try_acquire_lock(lock_key, consolidation_type, period_identifier)

    def release_consolidation_lock(self, consolidation_type: str, period_identifier: str) -> None:
        """Release a typed consolidation lock."""
        lock_key = f"tsdb:{consolidation_type}:{period_identifier}"
        self._release_lock(lock_key, consolidation_type, period_identifier)

    def acquire_period_lock(self, period_start: datetime) -> bool:
        """Acquire a per-6h-period lock for basic consolidation."""
        lock_key = f"tsdb:basic:{period_start.isoformat()}"
        return self._try_acquire_lock(lock_key, "basic", period_start.isoformat())

    def release_period_lock(self, period_start: datetime) -> None:
        """Release a per-6h-period lock."""
        lock_key = f"tsdb:basic:{period_start.isoformat()}"
        self._release_lock(lock_key, "basic", period_start.isoformat())

    # ------------------------------------------------------------------
    # Period state probes
    # ------------------------------------------------------------------

    def check_period_consolidated(self, period_start: datetime, period_end: Optional[datetime] = None) -> bool:
        """Return True iff a tsdb_summary already exists for this period."""
        engine = _engine()
        if engine is None:
            return False
        if period_end is None:
            period_end = period_start + timedelta(hours=6)
        from_iso = period_start.isoformat().replace("+00:00", "Z")
        to_iso = (period_end + timedelta(milliseconds=1)).isoformat().replace("+00:00", "Z")
        try:
            raw = engine.tsdb_query_summary_nodes(
                "tsdb_summary", "basic", _tenant(), from_iso, to_iso
            )
            rows = json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or [])
            return bool(isinstance(rows, list) and rows)
        except Exception as e:
            logger.warning("check_period_consolidated probe failed: %s", e)
            return False

    async def get_last_consolidated_period(self) -> Optional[datetime]:
        """Return the period_end of the most recent tsdb_summary."""
        engine = _engine()
        if engine is None:
            return None
        try:
            now = datetime.now(timezone.utc)
            # Pull the last 90 days of basic summaries DESC; take the newest period_end.
            from_iso = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")
            to_iso = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
            raw = engine.tsdb_query_summary_nodes(
                "tsdb_summary", "basic", _tenant(), from_iso, to_iso
            )
            rows = json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or [])
            if not isinstance(rows, list) or not rows:
                return None
            # Pick max period_end.
            latest: Optional[datetime] = None
            for attrs in rows:
                if not isinstance(attrs, dict):
                    continue
                pe_str = attrs.get("period_end")
                if not pe_str:
                    continue
                try:
                    pe_dt = datetime.fromisoformat(str(pe_str).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if latest is None or pe_dt > latest:
                    latest = pe_dt
            return latest
        except Exception as e:
            logger.warning("get_last_consolidated_period failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # Per-period node listing — used for stats counts + edge targets
    # ------------------------------------------------------------------

    def query_all_nodes_in_period(
        self, period_start: datetime, period_end: datetime
    ) -> Dict[str, TSDBNodeQueryResult]:
        """Return a per-node_type bucket of nodes updated in [start, end).

        Used by the consolidation loop for record-count stats and by
        `_ensure_summary_edges` to enumerate edge targets. Paginates persist's
        `cirisgraph_query_nodes` with `updated_after`/`updated_before` filters.
        """
        engine = _engine()
        buckets: Dict[str, TSDBNodeQueryResult] = {}
        if engine is None:
            return buckets

        # Walk every scope; persist requires `scope` in the filter.
        for scope in ("LOCAL", "COMMUNITY", "IDENTITY", "ENVIRONMENT"):
            filter_json = json.dumps({
                "scope": scope,
                "updated_after": period_start.isoformat().replace("+00:00", "Z"),
                "updated_before": period_end.isoformat().replace("+00:00", "Z"),
            })
            cursor_json = json.dumps({"version": "v1", "last_ts": "9999-12-31T23:59:59Z", "last_id": ""})
            while True:
                try:
                    raw = engine.cirisgraph_query_nodes(filter_json, cursor_json, 500)
                except Exception as e:
                    logger.warning("cirisgraph_query_nodes(%s) failed: %s", scope, e)
                    break
                parsed = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                items = parsed.get("items", []) if isinstance(parsed, dict) else []
                if not items:
                    break
                for row in items:
                    if not isinstance(row, dict):
                        continue
                    ntype = str(row.get("node_type", "unknown"))
                    bucket = buckets.get(ntype)
                    if bucket is None:
                        bucket = TSDBNodeQueryResult(
                            nodes=[], period_start=period_start, period_end=period_end
                        )
                        buckets[ntype] = bucket
                    bucket.nodes.append(row)
                if len(items) < 500:
                    break
                next_cursor = parsed.get("cursor") if isinstance(parsed, dict) else None
                if not next_cursor:
                    break
                cursor_json = next_cursor if isinstance(next_cursor, str) else json.dumps(next_cursor)
        return buckets

    # ------------------------------------------------------------------
    # Legacy table-init shim — persist owns the lock schema.
    # ------------------------------------------------------------------

    def _ensure_locks_table_exists(self) -> None:
        """No-op shim — persist owns `cirislens_maintenance_locks`."""
        return None
