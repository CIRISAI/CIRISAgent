import asyncio
from datetime import datetime, timezone

from ciris_engine.logic.persistence.db.core import get_db_connection

# First, delete existing SUMMARIZES edges to force recalculation
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute(
        """
        DELETE FROM graph_edges
        WHERE source_node_id = 'tsdb_summary_20250713_12'
          AND relationship = 'SUMMARIZES'
    """
    )
    deleted = cursor.rowcount
    conn.commit()
    print(f"Deleted {deleted} existing SUMMARIZES edges")

from ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager import EdgeManager
from ciris_engine.logic.services.graph.tsdb_consolidation.period_manager import PeriodManager
from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import QueryManager

# Now run the edge fix
from ciris_engine.logic.services.graph.tsdb_consolidation.service import TSDBConsolidationService


async def test_edge_fix():
    # Create minimal components
    edge_manager = EdgeManager()
    query_manager = QueryManager(memory_bus=None)
    period_manager = PeriodManager()

    # Create a minimal TSDB service
    tsdb_service = TSDBConsolidationService.__new__(TSDBConsolidationService)
    tsdb_service._edge_manager = edge_manager
    tsdb_service._query_manager = query_manager
    tsdb_service._period_manager = period_manager
    tsdb_service._memory_bus = None

    period_start = datetime(2025, 7, 13, 12, 0, 0, tzinfo=timezone.utc)
    period_end = datetime(2025, 7, 13, 18, 0, 0, tzinfo=timezone.utc)

    print("\nCalling _ensure_summary_edges with fresh query...")
    await tsdb_service._ensure_summary_edges(period_start, period_end)

    # Check final count
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM graph_edges
            WHERE source_node_id = 'tsdb_summary_20250713_12'
              AND relationship = 'SUMMARIZES'
        """
        )

        final_count = cursor.fetchone()["count"]
        print(f"\nFinal SUMMARIZES edges: {final_count}")

        # Check if config node has edge
        cursor.execute(
            """
            SELECT edge_id
            FROM graph_edges
            WHERE source_node_id = 'tsdb_summary_20250713_12'
              AND target_node_id = 'config:adaptive_filter.config'
              AND relationship = 'SUMMARIZES'
        """
        )

        if cursor.fetchone():
            print("✅ Config node now has SUMMARIZES edge!")
        else:
            print("❌ Config node still missing SUMMARIZES edge")


asyncio.run(test_edge_fix())
