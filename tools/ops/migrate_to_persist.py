#!/usr/bin/env python3
"""Migrate legacy graph_nodes/graph_edges into persist's cirisgraph_*.

Pre-A1 commit for CIRIS 2.9.0 persist absorption — see CIRISAgent#763.

Reads from agent's `ciris_engine.db`:
  - graph_nodes (PK: node_id, scope) — ~989 rows on datum
  - graph_edges (PK: edge_id)        — ~3730 rows on datum

Writes to persist's `cirisgraph_*` tables via persist's typed
`cirisgraph_upsert_node` / `cirisgraph_upsert_edge` APIs (CIRISPersist
v1.3.1+). The v1.3.1 release fixed CIRISPersist#49 — supplied
`created_at` / `updated_at` are now honored verbatim, so historical
timestamps from the legacy chain survive the round-trip.

Pre-v1.3.1 versions of this script wrote via direct SQL INSERT because
the upsert API stamped now() on every write; that workaround is gone.

Transformations applied:
  - scope: lowercase ('local','community','identity') -> UPPERCASE
    persist enum ('LOCAL','COMMUNITY','IDENTITY')
  - graph_nodes.created_at: legacy 'YYYY-MM-DD HH:MM:SS' (no TZ) ->
    RFC 3339 (UTC assumed) so persist's lexicographic time-window
    queries don't silently misbehave (the v1.2.0 maintenance gotcha)
  - updated_at fallback when NULL: copy created_at
  - updated_by fallback when NULL: 'legacy_unattributed'
  - attributes_json column -> attributes (rename, content unchanged)

Skipped (deliberate fresh-start semantics):
  - consolidation_locks: short-lived operational state, fresh-start safe
  - service_correlations: 70k+ rows of telemetry; persist's trace_events
    has a richer typed shape (cost_usd, deployment_*, scrub_*) that
    legacy rows can't populate — legacy table stays for backward-compat
    reads, new traces land in trace_events

Idempotent: gated by a sentinel file (`.persist_migrated` in the data
dir). To re-run in dev, remove the sentinel; do NOT do this in prod.

ServiceInitializer integration: on first 2.9.0 boot, if sentinel is
absent, run this script then write sentinel. See Lane A0 in #763.

Usage:
    python -m tools.ops.migrate_to_persist
    python -m tools.ops.migrate_to_persist --engine-db PATH --dry-run
    python -m tools.ops.migrate_to_persist --signing-key-id KEY_ID
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("migrate_to_persist")

# Scope mapping — agent uses lowercase, persist requires UPPERCASE
# (cirisgraph_nodes CHECK constraint: scope IN ('LOCAL','IDENTITY','ENVIRONMENT','COMMUNITY')).
# Agent has 3 scopes (no ENVIRONMENT historically); migration covers the 3 it sees.
SCOPE_MAP = {
    "local": "LOCAL",
    "community": "COMMUNITY",
    "identity": "IDENTITY",
    "environment": "ENVIRONMENT",
}

# Legacy datetime format from CURRENT_TIMESTAMP default (no TZ, no microseconds).
# 975 of 989 graph_nodes rows on datum use this; the rest are already RFC 3339.
_LEGACY_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_RFC3339_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def normalize_datetime(ts: Optional[str]) -> Optional[str]:
    """Convert legacy 'YYYY-MM-DD HH:MM:SS' to RFC 3339 (UTC).

    Already-RFC 3339 values pass through unchanged. NULL passes through
    so caller can decide on a fallback.
    """
    if ts is None or ts == "":
        return None
    if _RFC3339_RE.match(ts):
        return ts
    if _LEGACY_DT_RE.match(ts):
        # 'YYYY-MM-DD HH:MM:SS' -> 'YYYY-MM-DDTHH:MM:SS+00:00'
        return ts.replace(" ", "T", 1) + "+00:00"
    # Unknown format — keep verbatim and warn; caller decides
    logger.warning("unknown datetime format, keeping verbatim: %r", ts)
    return ts


def map_scope(scope: str) -> str:
    """Lowercase agent scope -> UPPERCASE persist enum.

    Raises ValueError on unrecognized scope so the migration fails loud
    rather than silently dropping rows with a typo'd scope.
    """
    s = SCOPE_MAP.get(scope.lower())
    if s is None:
        raise ValueError(f"unknown legacy scope: {scope!r}")
    return s


@dataclass
class MigrationStats:
    nodes_read: int = 0
    nodes_written: int = 0
    nodes_skipped_already_present: int = 0
    nodes_skipped_too_large: int = 0
    edges_read: int = 0
    edges_written: int = 0
    edges_skipped_already_present: int = 0
    edges_skipped_dangling_fk: int = 0
    errors: int = 0


# Persist v1.3.1 caps attributes payload at 1 MiB. Historical agent
# data (large conversation_summary blobs) can exceed this. Track + skip
# oversize rows; upstream ask filed for raising the cap or providing a
# bulk_import mode that bypasses it.
_PERSIST_ATTRS_CAP_BYTES = 1024 * 1024


def _parse_attrs(attrs_json: Any) -> Any:
    """Parse legacy attributes_json column into a dict for persist's
    typed payload. Persist json.dumps the value once on the way to
    storage, so we MUST hand it a dict (not a JSON string) — passing
    a string would double-encode."""
    import json as _json
    if attrs_json is None:
        return {}
    if isinstance(attrs_json, dict):
        return attrs_json
    if isinstance(attrs_json, str):
        try:
            return _json.loads(attrs_json) if attrs_json else {}
        except Exception:
            return {}
    return {}


def migrate_nodes(
    con: sqlite3.Connection,
    engine: Any,
    dry_run: bool,
    stats: MigrationStats,
) -> None:
    """Copy graph_nodes rows into cirisgraph_nodes via persist's typed
    `cirisgraph_upsert_node` API.

    Idempotent: query cirisgraph_nodes for each (node_id, scope) before
    upserting; skip if already present. Persist v1.3.1+ honors supplied
    `created_at` / `updated_at`, so historical timestamps survive.
    """
    import json as _json
    rows = con.execute(
        "SELECT node_id, scope, node_type, attributes_json, version, "
        "       updated_by, updated_at, created_at "
        "FROM graph_nodes"
    ).fetchall()
    stats.nodes_read = len(rows)

    for row in rows:
        node_id, scope, node_type, attrs_json, version, updated_by, updated_at, created_at = row
        try:
            new_scope = map_scope(scope)
            new_created = normalize_datetime(created_at)
            new_updated = normalize_datetime(updated_at) or new_created
            new_updated_by = updated_by or "legacy_unattributed"
            new_version = version if version is not None else 1

            # Skip if already present (idempotency under --force re-runs)
            existing = engine.cirisgraph_get_node(node_id, new_scope)
            if existing is not None:
                stats.nodes_skipped_already_present += 1
                continue

            # Skip if attributes blob exceeds persist's typed-API cap.
            # Legacy agent data has unbounded blobs (conversation_summary
            # can be 1.5+ MB on long-running agents); persist v1.3.1 caps
            # at 1 MiB. Documented data-loss; upstream ask filed.
            attrs_dict = _parse_attrs(attrs_json)
            attrs_size = len(_json.dumps(attrs_dict).encode("utf-8"))
            if attrs_size > _PERSIST_ATTRS_CAP_BYTES:
                logger.warning(
                    "node %s/%s skipped: attributes %d bytes > %d cap",
                    node_id, scope, attrs_size, _PERSIST_ATTRS_CAP_BYTES,
                )
                stats.nodes_skipped_too_large += 1
                continue

            if dry_run:
                continue

            payload = {
                "node_id": node_id,
                "scope": new_scope,
                "node_type": node_type,
                "attributes": attrs_dict,
                "version": new_version,
                "updated_by": new_updated_by,
                "updated_at": new_updated,
                "created_at": new_created,
            }
            engine.cirisgraph_upsert_node(_json.dumps(payload), 0)
            stats.nodes_written += 1
        except Exception as exc:
            logger.error("node migration failed for (%s, %s): %s", node_id, scope, exc)
            stats.errors += 1


def migrate_edges(
    con: sqlite3.Connection,
    engine: Any,
    dry_run: bool,
    stats: MigrationStats,
) -> None:
    """Copy graph_edges rows into cirisgraph_edges via persist's typed
    `cirisgraph_upsert_edge` API.

    Skip edges whose source or target node didn't make it into
    `cirisgraph_nodes` — persist's edge schema doesn't enforce the FK
    so the integrity check is on us. For idempotency we read the
    current set of present nodes once up front (one SELECT, not one
    per edge), and check edges_seen for already-written edge_ids.
    """
    import json as _json
    rows = con.execute(
        "SELECT edge_id, source_node_id, target_node_id, scope, relationship, "
        "       weight, attributes_json, created_at "
        "FROM graph_edges"
    ).fetchall()
    stats.edges_read = len(rows)

    # Snapshot of (node_id, scope) present in cirisgraph_nodes — used to
    # filter edges with dangling FK references. One SELECT, indexed lookup.
    present = set(
        con.execute("SELECT node_id, scope FROM cirisgraph_nodes").fetchall()
    )
    # Snapshot of edge_ids already in cirisgraph_edges — used for idempotency.
    existing_edges = set(
        eid for (eid,) in con.execute("SELECT edge_id FROM cirisgraph_edges").fetchall()
    )

    for row in rows:
        edge_id, src, tgt, scope, rel, weight, attrs_json, created_at = row
        try:
            new_scope = map_scope(scope)
            if (src, new_scope) not in present or (tgt, new_scope) not in present:
                stats.edges_skipped_dangling_fk += 1
                continue
            if edge_id in existing_edges:
                stats.edges_skipped_already_present += 1
                continue
            new_created = normalize_datetime(created_at)
            new_weight = float(weight) if weight is not None else 1.0

            if dry_run:
                continue

            payload = {
                "edge_id": edge_id,
                "source_node_id": src,
                "target_node_id": tgt,
                "scope": new_scope,
                "relationship": rel,
                "weight": new_weight,
                "attributes": _parse_attrs(attrs_json),
                "created_at": new_created,
            }
            engine.cirisgraph_upsert_edge(_json.dumps(payload))
            stats.edges_written += 1
        except Exception as exc:
            logger.error("edge migration failed for %s: %s", edge_id, exc)
            stats.errors += 1


def run(engine_db: Path, signing_key_id: str, dry_run: bool) -> MigrationStats:
    if not engine_db.exists():
        raise FileNotFoundError(f"engine DB not found: {engine_db}")

    from ciris_persist import Engine
    engine = Engine(f"sqlite:///{engine_db.resolve()}", signing_key_id)

    stats = MigrationStats()
    con = sqlite3.connect(str(engine_db))
    try:
        migrate_nodes(con, engine, dry_run, stats)
        migrate_edges(con, engine, dry_run, stats)
    finally:
        con.close()

    return stats


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--engine-db",
        type=Path,
        default=Path("data/ciris_engine.db"),
        help="Path to agent's ciris_engine.db (default: data/ciris_engine.db)",
    )
    parser.add_argument(
        "--signing-key-id",
        default="migration_bootstrap",
        help="Signing key ID for persist Engine bootstrap (default: migration_bootstrap)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read + validate + report counts; do not INSERT into cirisgraph_*",
    )
    parser.add_argument(
        "--sentinel",
        type=Path,
        default=None,
        help="Path to migration sentinel file (default: <engine-db parent>/.persist_migrated)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore sentinel file (re-run migration). Dev only — destructive in prod.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    sentinel = args.sentinel or args.engine_db.parent / ".persist_migrated"
    if sentinel.exists() and not args.force:
        logger.info("sentinel %s exists; migration already ran. Use --force to re-run.", sentinel)
        return 0

    logger.info("starting migration: engine_db=%s dry_run=%s", args.engine_db, args.dry_run)
    stats = run(args.engine_db, args.signing_key_id, args.dry_run)

    logger.info("nodes: read=%d written=%d already_present=%d too_large=%d errors=%d",
                stats.nodes_read, stats.nodes_written,
                stats.nodes_skipped_already_present,
                stats.nodes_skipped_too_large, stats.errors)
    logger.info("edges: read=%d written=%d already_present=%d dangling_fk=%d errors=%d",
                stats.edges_read, stats.edges_written,
                stats.edges_skipped_already_present,
                stats.edges_skipped_dangling_fk, stats.errors)

    if stats.errors:
        logger.error("migration completed with %d errors — sentinel NOT written", stats.errors)
        return 1

    if not args.dry_run:
        sentinel.write_text(
            json.dumps({
                "nodes_written": stats.nodes_written,
                "edges_written": stats.edges_written,
            })
        )
        logger.info("sentinel written: %s", sentinel)

    return 0


if __name__ == "__main__":
    sys.exit(main())
