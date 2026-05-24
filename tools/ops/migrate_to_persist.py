#!/usr/bin/env python3
"""A0a legacy-graph migration — thin CLI wrapper around ciris-persist.

Since ciris-persist v1.6.4 (CIRISPersist#70) the entire A0a migration —
reading the legacy 2.8.x `graph_nodes` / `graph_edges` tables and
re-upserting them into persist's `cirisgraph.*` schema — lives inside
persist's `engine.run_legacy_graph_migration(options_json)` substrate.
Persist reads the legacy schema over its own connection (SQLite *and*
Postgres), so the agent ships zero raw SQL for the upgrade path.

The agent's boot path (`_bootstrap_persist_engine` in
`ciris_engine/logic/persistence/db/core.py`) calls the substrate
directly. This module survives only as an ops/debug CLI — e.g. to run a
dry-run audit against a production DB, or to force a re-run.

Usage:
    python -m tools.ops.migrate_to_persist                       # SQLite default
    python -m tools.ops.migrate_to_persist --db-url sqlite:///path/to.db
    python -m tools.ops.migrate_to_persist --db-url postgresql://... --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("migrate_to_persist")


def run(
    db_url: str,
    signing_key_id: str = "migration_bootstrap",
    dry_run: bool = False,
    attributes_cap_bytes: Optional[int] = None,
    engine: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run the A0a legacy-graph migration via persist's substrate.

    Args:
        db_url: persist DSN — `sqlite:///abs/path.db` or `postgresql://...`.
        signing_key_id: scrub key id for any Engine constructed here.
        dry_run: if True, persist reads + size-checks every row but writes
            nothing.
        attributes_cap_bytes: optional per-call override of persist's 1 MiB
            attributes cap (None = persist default).
        engine: optional pre-constructed Engine. The agent boot path passes
            its already-wired Engine so a second instance isn't built
            against the same DB.

    Returns:
        The decoded `LegacyMigrationStats` dict from persist.
    """
    if engine is None:
        from ciris_persist import Engine  # type: ignore[import-untyped]

        engine = Engine(db_url, signing_key_id)

    options: Dict[str, Any] = {"dry_run": dry_run}
    if attributes_cap_bytes is not None:
        options["attributes_cap_bytes"] = attributes_cap_bytes

    raw = engine.run_legacy_graph_migration(json.dumps(options))
    stats: Dict[str, Any] = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
    return stats


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db-url",
        default=None,
        help="persist DSN (sqlite:///path or postgresql://...). "
        "Default: sqlite:/// of the agent's main DB.",
    )
    parser.add_argument(
        "--signing-key-id",
        default="migration_bootstrap",
        help="Signing key ID for persist Engine bootstrap.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read + validate + report counts; write nothing.",
    )
    parser.add_argument(
        "--attributes-cap-bytes",
        type=int,
        default=None,
        help="Override persist's 1 MiB attributes cap for this run.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_url = args.db_url
    if db_url is None:
        from ciris_engine.logic.config import get_sqlite_db_full_path

        db_url = f"sqlite:///{Path(get_sqlite_db_full_path()).resolve()}"

    logger.info("starting A0a migration: db_url=%s dry_run=%s", db_url, args.dry_run)
    stats = run(
        db_url=db_url,
        signing_key_id=args.signing_key_id,
        dry_run=args.dry_run,
        attributes_cap_bytes=args.attributes_cap_bytes,
    )

    logger.info(
        "nodes: read=%d written=%d already_present=%d too_large=%d",
        stats.get("nodes_read", 0), stats.get("nodes_written", 0),
        stats.get("nodes_skipped_already_present", 0),
        stats.get("nodes_skipped_too_large", 0),
    )
    logger.info(
        "edges: read=%d written=%d already_present=%d dangling_fk=%d",
        stats.get("edges_read", 0), stats.get("edges_written", 0),
        stats.get("edges_skipped_already_present", 0),
        stats.get("edges_skipped_dangling_fk", 0),
    )

    outcome = stats.get("outcome")
    errors = stats.get("errors", 0)
    if outcome not in ("ok", "partial") or errors:
        logger.error(
            "migration outcome=%s errors=%d first_error_at=%s",
            outcome, errors, stats.get("first_error_at_node_id"),
        )
        return 1
    logger.info("migration outcome=%s", outcome)
    return 0


if __name__ == "__main__":
    sys.exit(main())
