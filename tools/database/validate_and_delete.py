#!/usr/bin/env python3
"""
Validate and delete already consolidated data.
This script checks existing summaries and deletes the raw data if validation passes.
"""

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.insert(0, "/home/emoore/CIRISAgent")


def parse_period_id(period_id):
    """Convert period ID like '20250709_00' to start/end times."""
    date_str = period_id[:8]
    hour_str = period_id[9:]

    year = int(date_str[:4])
    month = int(date_str[4:6])
    day = int(date_str[6:8])
    hour = int(hour_str)

    start_time = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
    end_time = start_time + timedelta(hours=6)

    return start_time, end_time


def validate_and_delete_period(period_id, dry_run=False):
    """Validate a consolidated period and delete raw data if counts match."""

    start_time, end_time = parse_period_id(period_id)

    print(f"\nValidating period: {period_id} ({start_time} to {end_time})")
    print("=" * 80)

    conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
    cursor = conn.cursor()

    # Check if summaries exist
    cursor.execute(
        """
        SELECT node_id, node_type, attributes_json
        FROM graph_nodes
        WHERE node_type LIKE '%_summary'
          AND node_id LIKE '%_' || ?
        ORDER BY node_type
    """,
        (period_id,),
    )

    summaries = cursor.fetchall()

    if not summaries:
        print(f"No summaries found for period {period_id}")
        conn.close()
        return 0

    print(f"Found {len(summaries)} summaries")

    # Report before state
    print("\nBEFORE DELETION:")
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

    for node_type, count in cursor.fetchall():
        print(f"  {node_type}: {count:,}")

    # Validate each summary
    total_deleted = 0
    deletion_summary = defaultdict(int)

    for node_id, node_type, attrs_json in summaries:
        attrs = json.loads(attrs_json) if attrs_json else {}
        print(f"\n{node_type}: {node_id}")

        if node_type == "tsdb_summary":
            claimed_count = attrs.get("source_node_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} nodes")

            # Count actual tsdb_data nodes
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

            if claimed_count == actual_count and actual_count > 0:
                print("  ✓ Counts match!")
                if not dry_run:
                    print("  Deleting...")
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
                    print(f"  Deleted {deleted:,} tsdb_data nodes")
                    deletion_summary["tsdb_data"] = deleted
                    total_deleted += deleted
                else:
                    print("  [DRY RUN] Would delete nodes")
            else:
                print("  ✗ Count mismatch or no data! Not deleting.")

        elif node_type == "audit_summary":
            claimed_count = attrs.get("source_node_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} nodes")

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

            if claimed_count == actual_count and actual_count > 0:
                print("  ✓ Counts match!")
                if not dry_run:
                    print("  Deleting...")
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
                    print(f"  Deleted {deleted:,} audit_entry nodes")
                    deletion_summary["audit_entry"] = deleted
                    total_deleted += deleted
                else:
                    print("  [DRY RUN] Would delete nodes")

        elif node_type == "trace_summary":
            # Check correlations
            claimed_count = attrs.get("source_correlation_count", 0)
            print(f"  Claims to have consolidated: {claimed_count:,} correlations")

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

            if claimed_count == actual_count and actual_count > 0:
                print("  ✓ Counts match!")
                if not dry_run:
                    print("  Deleting...")
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
                    print("  [DRY RUN] Would delete correlations")

    if not dry_run:
        conn.commit()

    # Report after state
    if not dry_run and total_deleted > 0:
        print("\nAFTER DELETION:")
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

        remaining = cursor.fetchall()
        if remaining:
            for node_type, count in remaining:
                print(f"  {node_type}: {count:,}")
        else:
            print("  No nodes remaining in period")

    conn.close()

    # Summary
    print("\nSUMMARY:")
    if dry_run:
        print("  [DRY RUN] No changes made")
    else:
        print(f"  Total deleted: {total_deleted:,}")
        if deletion_summary:
            for item_type, count in deletion_summary.items():
                print(f"    {item_type}: {count:,}")

    return total_deleted


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate and delete consolidated TSDB data")
    parser.add_argument("--period", type=str, help="Period ID (YYYYMMDD_HH)")
    parser.add_argument("--all", action="store_true", help="Process all consolidated periods")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")

    args = parser.parse_args()

    if args.all:
        # Find all periods with summaries
        conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DISTINCT substr(node_id, -11) as period_id
            FROM graph_nodes
            WHERE node_type = 'tsdb_summary'
            ORDER BY period_id
        """
        )

        periods = [row[0] for row in cursor.fetchall()]
        conn.close()

        print(f"Found {len(periods)} consolidated periods")

        total_deleted_all = 0
        for period_id in periods:
            deleted = validate_and_delete_period(period_id, dry_run=args.dry_run)
            total_deleted_all += deleted

        print(f"\n{'='*80}")
        print(f"GRAND TOTAL: {total_deleted_all:,} records deleted across all periods")

    elif args.period:
        validate_and_delete_period(args.period, dry_run=args.dry_run)
    else:
        print("Error: Must specify either --period or --all")
        sys.exit(1)


if __name__ == "__main__":
    main()
