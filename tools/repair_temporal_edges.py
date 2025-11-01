#!/usr/bin/env python3
"""
Repair missing temporal edges between summary nodes.

This script fixes temporal edge chains broken by the v1.5.5 PostgreSQL bug where
hardcoded '?' placeholders caused DELETE and INSERT statements to fail.

Usage:
    # Dry run (show what would be fixed):
    python tools/repair_temporal_edges.py --dry-run

    # Actually repair:
    python tools/repair_temporal_edges.py

    # PostgreSQL with custom connection:
    python tools/repair_temporal_edges.py --db-url "postgresql://user:pass@host:port/dbname"
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Tuple
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, ".")

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter


def get_row_value(row, key, index=0):
    """Get value from row by key (dict-like) or index (tuple-like)."""
    if hasattr(row, "keys"):  # RealDictRow or dict
        return row[key]
    else:  # tuple
        return row[index]


def analyze_temporal_edges(db_path: str | None = None) -> dict:
    """Analyze current state of temporal edges."""
    print("🔍 Analyzing temporal edge state...")

    adapter = get_adapter()
    ph = adapter.placeholder()

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()

        # Get summary types
        cursor.execute(
            """
            SELECT DISTINCT node_type
            FROM graph_nodes
            WHERE node_type LIKE '%_summary'
            ORDER BY node_type
        """
        )

        rows = cursor.fetchall()
        summary_types = [get_row_value(row, "node_type", 0) for row in rows]

        results = {}

        for summary_type in summary_types:
            # Get all summaries of this type ordered by creation
            cursor.execute(
                f"""
                SELECT node_id, created_at
                FROM graph_nodes
                WHERE node_type = {ph}
                ORDER BY created_at
            """,
                (summary_type,),
            )

            summaries = cursor.fetchall()

            missing_next = 0
            missing_prev = 0
            has_duplicates = 0

            for i, row in enumerate(summaries):
                node_id = get_row_value(row, "node_id", 0)
                created_at = get_row_value(row, "created_at", 1)

                # Check temporal edges
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM graph_edges
                    WHERE source_node_id = {ph} AND relationship = 'TEMPORAL_NEXT'
                """,
                    (node_id,),
                )
                result = cursor.fetchone()
                next_count = get_row_value(result, "count", 0)

                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM graph_edges
                    WHERE source_node_id = {ph} AND relationship = 'TEMPORAL_PREV'
                """,
                    (node_id,),
                )
                result = cursor.fetchone()
                prev_count = get_row_value(result, "count", 0)

                # First summary should have NEXT but not PREV
                # Last summary should have NEXT (to itself) but not PREV
                # Middle summaries should have both

                if i == 0:  # First
                    if next_count == 0:
                        missing_next += 1
                elif i == len(summaries) - 1:  # Last
                    if next_count == 0:
                        missing_next += 1
                else:  # Middle
                    if next_count == 0:
                        missing_next += 1
                    if prev_count == 0:
                        missing_prev += 1

                if next_count > 1 or prev_count > 1:
                    has_duplicates += 1

            results[summary_type] = {
                "total": len(summaries),
                "missing_next": missing_next,
                "missing_prev": missing_prev,
                "has_duplicates": has_duplicates,
            }

    return results


def repair_temporal_edges(db_path: str | None = None, dry_run: bool = False) -> dict:
    """Repair missing temporal edges between summaries.

    For each summary type:
    1. Order summaries by creation time
    2. Create TEMPORAL_NEXT chain: summary[i] -> summary[i+1]
    3. Create TEMPORAL_PREV chain: summary[i] -> summary[i-1]
    4. Last summary gets TEMPORAL_NEXT to itself (marks as latest)

    Args:
        db_path: Database path (None for default)
        dry_run: If True, show what would be done without making changes

    Returns:
        Dictionary of repair statistics
    """
    print(f"{'🧪 DRY RUN: ' if dry_run else '🔧 '}Repairing temporal edges...")

    adapter = get_adapter()
    ph = adapter.placeholder()

    stats = {"edges_created": 0, "edges_deleted": 0, "summaries_processed": 0}

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()

        # Get summary types
        cursor.execute(
            """
            SELECT DISTINCT node_type
            FROM graph_nodes
            WHERE node_type LIKE '%_summary'
            ORDER BY node_type
        """
        )

        rows = cursor.fetchall()
        summary_types = [get_row_value(row, "node_type", 0) for row in rows]

        for summary_type in summary_types:
            print(f"\n  Processing {summary_type}...")

            # Get all summaries of this type ordered by creation
            cursor.execute(
                f"""
                SELECT node_id, created_at
                FROM graph_nodes
                WHERE node_type = {ph}
                ORDER BY created_at
            """,
                (summary_type,),
            )

            summaries = cursor.fetchall()

            for i, row in enumerate(summaries):
                node_id = get_row_value(row, "node_id", 0)

                # Delete existing temporal edges for this summary
                cursor.execute(
                    f"""
                    DELETE FROM graph_edges
                    WHERE source_node_id = {ph}
                      AND relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
                """,
                    (node_id,),
                )

                deleted = cursor.rowcount
                stats["edges_deleted"] += deleted

                # Create TEMPORAL_NEXT edge
                if i < len(summaries) - 1:
                    # Point to next summary
                    next_node = summaries[i + 1]
                    next_node_id = get_row_value(next_node, "node_id", 0)

                    edge_id = f"edge_{uuid4().hex[:8]}"
                    cursor.execute(
                        f"""
                        INSERT INTO graph_edges
                        (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                        (
                            edge_id,
                            node_id,
                            next_node_id,
                            "local",
                            "TEMPORAL_NEXT",
                            1.0,
                            json.dumps({"is_latest": False, "context": "Points to next period"}),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    stats["edges_created"] += 1
                    print(f"    ✓ {node_id} TEMPORAL_NEXT -> {next_node_id}")
                else:
                    # Last summary: point to itself
                    edge_id = f"edge_{uuid4().hex[:8]}"
                    cursor.execute(
                        f"""
                        INSERT INTO graph_edges
                        (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                        (
                            edge_id,
                            node_id,
                            node_id,
                            "local",
                            "TEMPORAL_NEXT",
                            1.0,
                            json.dumps({"is_latest": True, "context": "Current latest summary"}),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    stats["edges_created"] += 1
                    print(f"    ✓ {node_id} TEMPORAL_NEXT -> {node_id} (latest)")

                # Create TEMPORAL_PREV edge (except for first summary)
                if i > 0:
                    prev_node = summaries[i - 1]
                    prev_node_id = get_row_value(prev_node, "node_id", 0)

                    edge_id = f"edge_{uuid4().hex[:8]}"
                    cursor.execute(
                        f"""
                        INSERT INTO graph_edges
                        (edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)
                        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                    """,
                        (
                            edge_id,
                            node_id,
                            prev_node_id,
                            "local",
                            "TEMPORAL_PREV",
                            1.0,
                            json.dumps({"context": "Points to previous period"}),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    stats["edges_created"] += 1
                    print(f"    ✓ {node_id} TEMPORAL_PREV -> {prev_node_id}")

                stats["summaries_processed"] += 1

        if not dry_run:
            conn.commit()
            print("\n✅ Changes committed to database")
        else:
            print("\n🧪 DRY RUN - No changes made")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Repair missing temporal edges between summaries")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--db-url", help="Database URL (PostgreSQL connection string)")

    args = parser.parse_args()

    print("=" * 80)
    print("CIRIS Temporal Edge Repair Tool")
    print("=" * 80)

    # Analyze current state
    analysis = analyze_temporal_edges(db_path=args.db_url)

    print("\n📊 Current State:")
    for summary_type, info in analysis.items():
        print(f"\n  {summary_type}:")
        print(f"    Total summaries: {info['total']}")
        print(f"    Missing TEMPORAL_NEXT: {info['missing_next']}")
        print(f"    Missing TEMPORAL_PREV: {info['missing_prev']}")
        print(f"    Has duplicates: {info['has_duplicates']}")

    total_issues = sum(
        info["missing_next"] + info["missing_prev"] + info["has_duplicates"] for info in analysis.values()
    )

    if total_issues == 0:
        print("\n✅ No temporal edge issues found!")
        return 0

    print(f"\n⚠️  Found {total_issues} issues to repair")

    if not args.dry_run:
        response = input("\nProceed with repair? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Repair cancelled")
            return 1

    # Repair
    stats = repair_temporal_edges(db_path=args.db_url, dry_run=args.dry_run)

    print("\n" + "=" * 80)
    print("📊 Repair Summary:")
    print(f"  Summaries processed: {stats['summaries_processed']}")
    print(f"  Edges deleted: {stats['edges_deleted']}")
    print(f"  Edges created: {stats['edges_created']}")
    print("=" * 80)

    if not args.dry_run:
        print("\n✅ Temporal edge repair completed successfully!")
        print(
            "\n💡 Verify with: SELECT node_type, COUNT(*) FROM graph_edges WHERE relationship LIKE 'TEMPORAL_%' GROUP BY node_type;"
        )
    else:
        print("\n🧪 Dry run completed. Use without --dry-run to apply changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
