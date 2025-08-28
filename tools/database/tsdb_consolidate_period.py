#!/usr/bin/env python3
"""
Consolidate and optionally delete data for a specific TSDB period.

Usage:
    python consolidate_period.py --start "2025-07-03 12:00:00" --end "2025-07-03 18:00:00"
    python consolidate_period.py --start "2025-07-03 12:00:00" --end "2025-07-03 18:00:00" --delete
    python consolidate_period.py --period "20250703_12"  # Auto-calculates 6-hour period
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, "/home/emoore/CIRISAgent")

from test_consolidation_full import run_full_consolidation


def parse_period_id(period_id):
    """Convert period ID like '20250703_12' to start/end times."""
    # Parse YYYYMMDD_HH format
    date_str = period_id[:8]
    hour_str = period_id[9:]

    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:8])
    hour = int(hour_str)

    start_time = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
    end_time = start_time + timedelta(hours=6)

    return start_time, end_time


def report_before_state(start_time, end_time):
    """Report the state before consolidation."""
    conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
    cursor = conn.cursor()

    print("=" * 80)
    print(f"BEFORE CONSOLIDATION - Period: {start_time} to {end_time}")
    print("=" * 80)

    # Count nodes by type in period
    cursor.execute(
        """
        SELECT node_type, COUNT(*) as count
        FROM graph_nodes
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        GROUP BY node_type
        ORDER BY count DESC
    """,
        (start_time.isoformat(), end_time.isoformat()),
    )

    print("\nNodes in period:")
    total_nodes = 0
    node_counts = {}
    for node_type, count in cursor.fetchall():
        print(f"  {node_type}: {count:,}")
        node_counts[node_type] = count
        total_nodes += count
    print(f"  TOTAL: {total_nodes:,}")

    # Count edges
    cursor.execute(
        """
        SELECT COUNT(*) FROM graph_edges
    """
    )
    edge_count = cursor.fetchone()[0]
    print(f"\nTotal edges in database: {edge_count:,}")

    # Count service correlations in period (in same database)
    cursor.execute(
        """
        SELECT COUNT(*) FROM service_correlations
        WHERE datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
    """,
        (start_time.isoformat(), end_time.isoformat()),
    )
    corr_count = cursor.fetchone()[0]
    print(f"\nService correlations in period: {corr_count:,}")

    # Count audit entries
    conn_audit = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_audit.db")
    cursor_audit = conn_audit.cursor()

    cursor_audit.execute(
        """
        SELECT COUNT(*) FROM audit_log_v2
        WHERE datetime(event_timestamp) >= datetime(?)
          AND datetime(event_timestamp) < datetime(?)
    """,
        (start_time.isoformat(), end_time.isoformat()),
    )
    audit_count = cursor_audit.fetchone()[0]
    print(f"Audit entries in period: {audit_count:,}")

    conn.close()
    conn_audit.close()

    return total_nodes, corr_count, audit_count, node_counts


async def run_consolidation_period(start_time, end_time):
    """Run consolidation for specific period."""
    print("\n" + "=" * 80)
    print("RUNNING CONSOLIDATION")
    print("=" * 80)

    # Call the full consolidation function with specific period
    summary_count = await run_full_consolidation(specific_start=start_time, specific_end=end_time)

    return summary_count


def validate_and_delete(start_time, end_time):
    """Validate consolidation claims and delete consolidated data."""
    print("\n" + "=" * 80)
    print("VALIDATING AND DELETING CONSOLIDATED DATA")
    print("=" * 80)

    conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
    cursor = conn.cursor()

    # Get summaries for this period
    cursor.execute(
        """
        SELECT node_id, node_type, attributes_json
        FROM graph_nodes
        WHERE node_type LIKE '%_summary'
          AND datetime(created_at) = datetime(?)
        ORDER BY node_type
    """,
        (end_time.isoformat(),),
    )

    summaries = cursor.fetchall()
    print(f"\nFound {len(summaries)} summaries to validate")

    total_deleted = 0
    deletion_summary = defaultdict(int)

    for node_id, node_type, attrs_json in summaries:
        attrs = json.loads(attrs_json) if attrs_json else {}
        print(f"\n{node_type}: {node_id}")

        if node_type == "tsdb_summary":
            claimed_count = attrs.get("source_node_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} TSDB nodes")

            # Validate
            cursor.execute(
                """
                SELECT COUNT(*) FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                  AND datetime(created_at) >= datetime(?)
                  AND datetime(created_at) < datetime(?)
            """,
                (start_time.isoformat(), end_time.isoformat()),
            )
            actual_count = cursor.fetchone()[0]
            print(f"  Actual count in database: {actual_count:,}")

            if claimed_count == actual_count:
                print("  ✓ Counts match! Deleting...")
                cursor.execute(
                    """
                    DELETE FROM graph_nodes
                    WHERE node_type = 'tsdb_data'
                      AND datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                """,
                    (start_time.isoformat(), end_time.isoformat()),
                )
                deleted = cursor.rowcount
                print(f"  Deleted {deleted:,} TSDB nodes")
                deletion_summary["tsdb_data"] = deleted
                total_deleted += deleted
            else:
                print("  ✗ COUNT MISMATCH! Not deleting.")

        elif node_type == "audit_summary":
            claimed_count = attrs.get("source_node_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} audit entries")

            # Validate
            cursor.execute(
                """
                SELECT COUNT(*) FROM graph_nodes
                WHERE node_type = 'audit_entry'
                  AND datetime(created_at) >= datetime(?)
                  AND datetime(created_at) < datetime(?)
            """,
                (start_time.isoformat(), end_time.isoformat()),
            )
            actual_count = cursor.fetchone()[0]
            print(f"  Actual count in database: {actual_count:,}")

            if claimed_count == actual_count:
                print("  ✓ Counts match! Deleting...")
                cursor.execute(
                    """
                    DELETE FROM graph_nodes
                    WHERE node_type = 'audit_entry'
                      AND datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                """,
                    (start_time.isoformat(), end_time.isoformat()),
                )
                deleted = cursor.rowcount
                print(f"  Deleted {deleted:,} audit entries")
                deletion_summary["audit_entry"] = deleted
                total_deleted += deleted
            else:
                print("  ✗ COUNT MISMATCH! Not deleting.")

        elif node_type == "trace_summary":
            # Delete service correlations (in same database)
            claimed_count = attrs.get("source_correlation_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} correlations")

            # Validate
            cursor.execute(
                """
                SELECT COUNT(*) FROM service_correlations
                WHERE datetime(created_at) >= datetime(?)
                  AND datetime(created_at) < datetime(?)
            """,
                (start_time.isoformat(), end_time.isoformat()),
            )
            actual_count = cursor.fetchone()[0]
            print(f"  Actual count in database: {actual_count:,}")

            if claimed_count == actual_count:
                print("  ✓ Counts match! Deleting...")
                cursor.execute(
                    """
                    DELETE FROM service_correlations
                    WHERE datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                """,
                    (start_time.isoformat(), end_time.isoformat()),
                )
                deleted = cursor.rowcount
                print(f"  Deleted {deleted:,} correlations")
                deletion_summary["service_correlations"] = deleted
                total_deleted += deleted
            else:
                print("  ✗ COUNT MISMATCH! Not deleting.")

    conn.commit()
    conn.close()

    return total_deleted, deletion_summary


def report_after_state():
    """Report the state after consolidation and deletion."""
    conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
    cursor = conn.cursor()

    print("\n" + "=" * 80)
    print("AFTER CONSOLIDATION AND DELETION")
    print("=" * 80)

    # Count all nodes by type
    cursor.execute(
        """
        SELECT node_type, COUNT(*) as count
        FROM graph_nodes
        GROUP BY node_type
        ORDER BY count DESC
    """
    )

    print("\nAll nodes remaining:")
    total_nodes = 0
    for node_type, count in cursor.fetchall():
        print(f"  {node_type}: {count:,}")
        total_nodes += count
    print(f"  TOTAL: {total_nodes:,}")

    # Count edges
    cursor.execute(
        """
        SELECT COUNT(*) FROM graph_edges
    """
    )
    edge_count = cursor.fetchone()[0]
    print(f"\nTotal edges: {edge_count:,}")

    # Show summaries
    cursor.execute(
        """
        SELECT node_id, attributes_json
        FROM graph_nodes
        WHERE node_type LIKE '%_summary'
        ORDER BY created_at DESC
        LIMIT 10
    """
    )

    print("\nLatest summaries:")
    for node_id, attrs_json in cursor.fetchall():
        attrs = json.loads(attrs_json) if attrs_json else {}
        period_start = attrs.get("period_start", "?")
        print(f"  {node_id} (period: {period_start})")

    conn.close()


async def main():
    parser = argparse.ArgumentParser(description="Consolidate TSDB data for a specific period")
    parser.add_argument("--start", type=str, help="Start time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end", type=str, help="End time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--period", type=str, help="Period ID (YYYYMMDD_HH) - alternative to start/end")
    parser.add_argument("--delete", action="store_true", help="Delete consolidated data after validation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")

    args = parser.parse_args()

    # Determine time range
    if args.period:
        start_time, end_time = parse_period_id(args.period)
    elif args.start and args.end:
        start_time = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end_time = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    else:
        print("Error: Must specify either --period or both --start and --end")
        sys.exit(1)

    # Report before state
    nodes_before, corr_before, audit_before, node_counts = report_before_state(start_time, end_time)

    if args.dry_run:
        print("\n" + "=" * 80)
        print("DRY RUN - No changes will be made")
        print("=" * 80)
        print("\nWould consolidate:")
        print(f"  Period: {start_time} to {end_time}")
        print(f"  Nodes: {nodes_before:,}")
        print(f"  Correlations: {corr_before:,}")
        print(f"  Audit entries: {audit_before:,}")
        if args.delete:
            print("\nWould then delete all consolidated data")
        return

    # Run consolidation
    summary_count = await run_consolidation_period(start_time, end_time)

    # Optionally delete
    if args.delete:
        deleted_count, deletion_summary = validate_and_delete(start_time, end_time)
    else:
        deleted_count = 0
        deletion_summary = {}

    # Report after
    report_after_state()

    # Final summary
    print("\n" + "=" * 80)
    print("CONSOLIDATION SUMMARY")
    print("=" * 80)
    print(f"Period: {start_time} to {end_time}")
    print("\nBefore:")
    print(f"  Nodes in period: {nodes_before:,}")
    print(f"  Correlations in period: {corr_before:,}")
    print(f"  Audit entries in period: {audit_before:,}")
    print("\nConsolidation:")
    print(f"  Summaries created: {summary_count}")
    if args.delete:
        print(f"  Records deleted: {deleted_count:,}")
        if deletion_summary:
            print("\n  Deletion breakdown:")
            for node_type, count in deletion_summary.items():
                print(f"    {node_type}: {count:,}")
    print("\nResult:")
    if args.delete:
        print(f"  Successfully consolidated {deleted_count:,} records into {summary_count} summaries")
    else:
        print(f"  Successfully created {summary_count} summaries (data retained)")


if __name__ == "__main__":
    asyncio.run(main())
