#!/usr/bin/env python3
"""
Run consolidation on specific periods using the test infrastructure.
"""

import asyncio
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/emoore/CIRISAgent")

# Import test components
from test_consolidation_direct import run_direct_consolidation


async def consolidate_periods():
    """Consolidate specific periods."""

    # Period 1: July 2nd 18:00-24:00
    period1_start = datetime(2025, 7, 2, 18, 0, 0, tzinfo=timezone.utc)
    period1_end = datetime(2025, 7, 3, 0, 0, 0, tzinfo=timezone.utc)

    # Period 2: July 3rd 00:00-06:00
    period2_start = datetime(2025, 7, 3, 0, 0, 0, tzinfo=timezone.utc)
    period2_end = datetime(2025, 7, 3, 6, 0, 0, tzinfo=timezone.utc)

    print("CONSOLIDATING TWO SEQUENTIAL PERIODS")
    print("=" * 80)

    # Clean up
    conn = sqlite3.connect("data/ciris_engine.db")
    cursor = conn.cursor()

    for period_id in ["20250702_18", "20250703_00"]:
        cursor.execute(
            """
            DELETE FROM graph_edges
            WHERE source_node_id LIKE '%_' || ?
               OR target_node_id LIKE '%_' || ?
        """,
            (period_id, period_id),
        )

        cursor.execute(
            """
            DELETE FROM graph_nodes
            WHERE node_id LIKE '%_' || ?
        """,
            (period_id,),
        )

    conn.commit()

    # Run Period 1
    print(f"\nPERIOD 1: {period1_start} to {period1_end}")
    print("-" * 80)
    summaries1 = await run_direct_consolidation(period1_start, period1_end)

    # Run Period 2
    print(f"\n\nPERIOD 2: {period2_start} to {period2_end}")
    print("-" * 80)
    summaries2 = await run_direct_consolidation(period2_start, period2_end)

    # Verify temporal chains
    print("\n\n" + "=" * 80)
    print("VERIFYING TEMPORAL CHAINS")
    print("=" * 80)

    cursor.execute(
        """
        SELECT
            n.node_id,
            n.node_type,
            GROUP_CONCAT(
                CASE
                    WHEN e.relationship = 'TEMPORAL_NEXT' THEN 'NEXT->' || e.target_node_id
                    WHEN e.relationship = 'TEMPORAL_PREV' THEN 'PREV->' || e.target_node_id
                END, ' | '
            ) as edges
        FROM graph_nodes n
        LEFT JOIN graph_edges e ON n.node_id = e.source_node_id
            AND e.relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
        WHERE n.node_id LIKE '%_20250702_18' OR n.node_id LIKE '%_20250703_00'
        GROUP BY n.node_id
        ORDER BY n.node_type, n.node_id
    """
    )

    current_type = None
    for node_id, node_type, edges in cursor.fetchall():
        if node_type != current_type:
            print(f"\n{node_type}:")
            current_type = node_type

        print(f"  {node_id}")
        if edges:
            for edge in edges.split(" | "):
                if edge:
                    rel, target = edge.split("->")
                    is_self = "(self)" if target == node_id else ""
                    print(f"    {rel} -> {target} {is_self}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(consolidate_periods())
