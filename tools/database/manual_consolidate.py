#!/usr/bin/env python3
"""
Manual consolidation script that uses the actual TSDBConsolidationService logic.
This ensures we use the exact same consolidation logic as the automated service.
"""

import asyncio
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

# Add project root to path
sys.path.insert(0, "/home/emoore/CIRISAgent")

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.services.graph.tsdb_consolidation.service import TSDBConsolidationService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol


class MockTimeService(TimeServiceProtocol):
    """Mock time service for testing."""

    def get_current_time(self) -> datetime:
        return datetime.now(timezone.utc)

    def get_timezone(self) -> timezone:
        return timezone.utc

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def run_manual_consolidation(
    period_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    delete_after: bool = False,
):
    """Run consolidation for a specific period using the actual service."""

    # Parse period if provided
    if period_id:
        # Parse YYYYMMDD_HH format
        date_str = period_id[:8]
        hour_str = period_id[9:]

        year = int(date_str[:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        hour = int(hour_str)

        start_time = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=6)

    print(f"Consolidating period: {start_time} to {end_time}")

    # Create minimal service registry
    registry = ServiceRegistry()

    # Create mock time service
    time_service = MockTimeService()

    # Create memory bus
    memory_bus = MemoryBus(registry, time_service)

    # Create consolidation service
    service = TSDBConsolidationService(service_registry=registry, memory_bus=memory_bus, time_service=time_service)

    # Initialize the service
    await service.initialize()

    # Get database connections
    conn = sqlite3.connect("/home/emoore/CIRISAgent/data/ciris_engine.db")
    cursor = conn.cursor()

    # Report before state
    print("\n" + "=" * 80)
    print("BEFORE CONSOLIDATION")
    print("=" * 80)

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
    total_before = 0
    node_counts = {}
    for node_type, count in cursor.fetchall():
        print(f"  {node_type}: {count:,}")
        node_counts[node_type] = count
        total_before += count
    print(f"  TOTAL: {total_before:,}")

    # Run consolidation using the service's internal method
    print("\n" + "=" * 80)
    print("RUNNING CONSOLIDATION")
    print("=" * 80)

    summaries = await service._consolidate_period(start_time, end_time)

    print(f"\nCreated {len(summaries)} summaries")

    # Report after state
    print("\n" + "=" * 80)
    print("AFTER CONSOLIDATION")
    print("=" * 80)

    # Check summaries created
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

    summaries_found = cursor.fetchall()
    print(f"\nSummaries created: {len(summaries_found)}")

    # Validate and optionally delete
    if delete_after:
        print("\n" + "=" * 80)
        print("VALIDATING AND DELETING")
        print("=" * 80)

        total_deleted = 0

        for node_id, node_type, attrs_json in summaries_found:
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
                print(f"  Actual count: {actual_count:,}")

                if claimed_count == actual_count and actual_count > 0:
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
                    print(f"  Deleted {deleted:,} tsdb_data nodes")
                    total_deleted += deleted
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
                print(f"  Actual count: {actual_count:,}")

                if claimed_count == actual_count and actual_count > 0:
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
                    print(f"  Deleted {deleted:,} audit_entry nodes")
                    total_deleted += deleted

            elif node_type == "trace_summary":
                # Delete correlations
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
                print(f"  Actual count: {actual_count:,}")

                if claimed_count == actual_count and actual_count > 0:
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
                    total_deleted += deleted

        conn.commit()
        print(f"\nTotal deleted: {total_deleted:,}")

    # Cleanup
    conn.close()
    await service.stop()

    print("\n" + "=" * 80)
    print("DONE")
    print("=" * 80)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Manually run TSDB consolidation")
    parser.add_argument("--period", type=str, help="Period ID (YYYYMMDD_HH)")
    parser.add_argument("--start", type=str, help="Start time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--end", type=str, help="End time (YYYY-MM-DD HH:MM:SS)")
    parser.add_argument("--delete", action="store_true", help="Delete consolidated data after validation")

    args = parser.parse_args()

    if args.period:
        await run_manual_consolidation(period_id=args.period, delete_after=args.delete)
    elif args.start and args.end:
        start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        await run_manual_consolidation(start_time=start, end_time=end, delete_after=args.delete)
    else:
        print("Error: Must specify either --period or both --start and --end")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
