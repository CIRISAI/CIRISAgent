"""
Storage and edge analysis for TSDB consolidation.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from .base import BaseDBTool, ReportFormatter


class StorageAnalyzer(BaseDBTool):
    """Analyze storage usage and edge statistics."""

    def get_storage_by_time_period(self) -> Dict[str, Any]:
        """Get storage statistics broken down by time period."""
        now = datetime.now(timezone.utc)

        periods = {
            "last_24_hours": (now - timedelta(hours=24), now),
            "last_week": (now - timedelta(days=7), now),
            "last_month": (now - timedelta(days=30), now),
            "total": (None, None),
        }

        storage_stats = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for period_name, (start, end) in periods.items():
                stats = {"nodes": 0, "edges": 0, "by_node_type": {}, "size_estimate_mb": 0}

                # Query for nodes
                if period_name == "total":
                    cursor.execute(
                        """
                        SELECT node_type, COUNT(*) as count,
                               SUM(LENGTH(attributes_json)) as json_size
                        FROM graph_nodes
                        GROUP BY node_type
                    """
                    )
                else:
                    cursor.execute(
                        """
                        SELECT node_type, COUNT(*) as count,
                               SUM(LENGTH(attributes_json)) as json_size
                        FROM graph_nodes
                        WHERE datetime(created_at) >= datetime(?)
                          AND datetime(created_at) <= datetime(?)
                        GROUP BY node_type
                    """,
                        (start.isoformat(), end.isoformat()),
                    )

                total_json_size = 0
                for row in cursor:
                    stats["by_node_type"][row["node_type"]] = row["count"]
                    stats["nodes"] += row["count"]
                    total_json_size += row["json_size"] or 0

                # Query for edges
                if period_name == "total":
                    cursor.execute(
                        """
                        SELECT COUNT(*) as count
                        FROM graph_edges
                    """
                    )
                else:
                    cursor.execute(
                        """
                        SELECT COUNT(*) as count
                        FROM graph_edges
                        WHERE datetime(created_at) >= datetime(?)
                          AND datetime(created_at) <= datetime(?)
                    """,
                        (start.isoformat(), end.isoformat()),
                    )

                row = cursor.fetchone()
                stats["edges"] = row["count"] if row else 0

                # Estimate size (rough calculation)
                # Base overhead per row ~200 bytes + JSON content
                node_size = (stats["nodes"] * 200 + total_json_size) / (1024 * 1024)
                edge_size = (stats["edges"] * 150) / (1024 * 1024)  # Edges are smaller
                stats["size_estimate_mb"] = node_size + edge_size

                storage_stats[period_name] = stats

        return storage_stats

    def get_edge_statistics_for_consolidated_periods(self) -> Dict[str, Any]:
        """Get edge statistics specifically for consolidated periods."""
        edge_stats = {
            "by_summary_period": {},
            "average_edges_per_summary": 0,
            "average_edges_per_node": 0,
            "total_summarizes_edges": 0,
            "total_consolidation_edges": 0,
            "total_summaries": 0,
            "periods_with_no_edges": [],
            "edge_coverage": 0,
            "edge_types": {},
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # First, get all consolidation-related edge types from summaries
            cursor.execute(
                """
                SELECT e.relationship, COUNT(*) as count
                FROM graph_edges e
                INNER JOIN graph_nodes n ON e.source_node_id = n.node_id
                WHERE n.node_type LIKE '%_summary'
                  AND e.relationship NOT IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV', 'TEMPORAL_CORRELATION')
                GROUP BY e.relationship
            """
            )

            consolidation_edge_types = {}
            for row in cursor:
                consolidation_edge_types[row["relationship"]] = row["count"]
                edge_stats["total_consolidation_edges"] += row["count"]

            edge_stats["edge_types"] = consolidation_edge_types

            # Get all summary nodes (not just tsdb)
            cursor.execute(
                """
                SELECT
                    node_id,
                    node_type,
                    json_extract(attributes_json, '$.period_start') as period_start,
                    json_extract(attributes_json, '$.period_end') as period_end,
                    json_extract(attributes_json, '$.consolidation_level') as level
                FROM graph_nodes
                WHERE node_type LIKE '%_summary'
                  AND (json_extract(attributes_json, '$.consolidation_level') = 'basic'
                       OR json_extract(attributes_json, '$.consolidation_level') IS NULL)
                ORDER BY period_start DESC
            """
            )

            summaries = cursor.fetchall()

            total_nodes_in_periods = 0
            total_edges_to_nodes = 0

            # Group summaries by period for better analysis
            periods = {}
            for summary in summaries:
                period_start = summary["period_start"]
                period_end = summary["period_end"]
                period_key = f"{period_start} to {period_end}"

                if period_key not in periods:
                    periods[period_key] = {"summaries": [], "period_start": period_start, "period_end": period_end}
                periods[period_key]["summaries"].append(summary)

            edge_stats["total_summaries"] = len(summaries)

            # Analyze each period
            for period_key, period_data in periods.items():
                period_start = period_data["period_start"]
                period_end = period_data["period_end"]

                # Count nodes created in this period
                cursor.execute(
                    """
                    SELECT COUNT(*) as node_count
                    FROM graph_nodes
                    WHERE scope = 'local'
                      AND node_type NOT LIKE '%_summary'
                      AND node_type != 'tsdb_data'
                      AND datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                """,
                    (period_start, period_end),
                )

                node_count = cursor.fetchone()["node_count"]

                # Count ALL edges TO nodes in this period from ALL summaries of this period
                cursor.execute(
                    """
                    SELECT COUNT(*) as edge_count
                    FROM graph_edges e
                    INNER JOIN graph_nodes target ON e.target_node_id = target.node_id
                    INNER JOIN graph_nodes source ON e.source_node_id = source.node_id
                    WHERE target.scope = 'local'
                      AND target.node_type NOT LIKE '%_summary'
                      AND target.node_type != 'tsdb_data'
                      AND datetime(target.created_at) >= datetime(?)
                      AND datetime(target.created_at) < datetime(?)
                      AND source.node_type LIKE '%_summary'
                      AND json_extract(source.attributes_json, '$.period_start') = ?
                """,
                    (period_start, period_end, period_start),
                )

                edges_to_period_nodes = cursor.fetchone()["edge_count"]

                period_stats = {
                    "nodes_in_period": node_count,
                    "edges_to_nodes": edges_to_period_nodes,
                    "average_edges_per_node": (edges_to_period_nodes / node_count) if node_count > 0 else 0,
                    "summary_count": len(period_data["summaries"]),
                }

                edge_stats["by_summary_period"][period_key] = period_stats

                if edges_to_period_nodes == 0 and node_count > 0:
                    edge_stats["periods_with_no_edges"].append(period_key)

                total_nodes_in_periods += node_count
                total_edges_to_nodes += edges_to_period_nodes

            # Calculate average
            if total_nodes_in_periods > 0:
                edge_stats["average_edges_per_node"] = total_edges_to_nodes / total_nodes_in_periods
                edge_stats["edge_coverage"] = (total_edges_to_nodes / total_nodes_in_periods) * 100

        return edge_stats

    def get_orphaned_nodes_analysis(self) -> Dict[str, Any]:
        """Analyze orphaned nodes within consolidated periods."""
        analysis = {
            "orphaned_in_consolidated": [],
            "by_type": defaultdict(int),
            "by_period": {},
            "total_orphaned": 0,
            "recommendations": [],
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get consolidated periods
            cursor.execute(
                """
                SELECT
                    node_id as summary_id,
                    json_extract(attributes_json, '$.period_start') as period_start,
                    json_extract(attributes_json, '$.period_end') as period_end
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                ORDER BY period_start DESC
            """
            )

            for period in cursor.fetchall():
                summary_id = period["summary_id"]
                period_start = period["period_start"]
                period_end = period["period_end"]

                # Find orphaned nodes in this period
                cursor.execute(
                    """
                    SELECT n.node_id, n.node_type, n.created_at
                    FROM graph_nodes n
                    WHERE n.scope = 'local'
                      AND n.node_type != 'tsdb_data'
                      AND datetime(n.created_at) >= datetime(?)
                      AND datetime(n.created_at) < datetime(?)
                      AND NOT EXISTS (
                          SELECT 1 FROM graph_edges e
                          WHERE e.source_node_id = ?
                            AND e.target_node_id = n.node_id
                            AND e.relationship = 'SUMMARIZES'
                      )
                """,
                    (period_start, period_end, summary_id),
                )

                orphaned = cursor.fetchall()
                if orphaned:
                    period_key = f"{period_start} to {period_end}"
                    analysis["by_period"][period_key] = {
                        "count": len(orphaned),
                        "summary_id": summary_id,
                        "nodes": [{"id": n["node_id"], "type": n["node_type"]} for n in orphaned[:5]],
                    }

                    for node in orphaned:
                        analysis["by_type"][node["node_type"]] += 1
                        analysis["total_orphaned"] += 1

        # Generate recommendations
        if analysis["total_orphaned"] > 0:
            analysis["recommendations"].append(
                {
                    "severity": "HIGH",
                    "issue": f"{analysis['total_orphaned']} orphaned nodes found in consolidated periods",
                    "action": "Run edge recalculation for affected periods",
                }
            )

        return analysis

    def print_comprehensive_storage_report(self):
        """Print comprehensive storage and edge analysis report."""
        formatter = ReportFormatter()
        formatter.print_section("COMPREHENSIVE TSDB STORAGE ANALYSIS")

        # Storage by time period
        storage_stats = self.get_storage_by_time_period()

        formatter.print_subsection("Data Storage by Time Period")

        for period, stats in storage_stats.items():
            period_label = period.replace("_", " ").title()
            print(f"\n{period_label}:")
            print(f"  Total Nodes: {stats['nodes']:,}")
            print(f"  Total Edges: {stats['edges']:,}")
            print(f"  Size Estimate: {stats['size_estimate_mb']:.2f} MB")

            if stats["by_node_type"]:
                print("  Node Types:")
                for node_type, count in sorted(stats["by_node_type"].items(), key=lambda x: x[1], reverse=True)[:5]:
                    print(f"    {node_type}: {count:,}")

        # Edge statistics for consolidated periods
        edge_stats = self.get_edge_statistics_for_consolidated_periods()

        formatter.print_subsection("Edge Statistics for Consolidated Periods")
        print(f"Total Summaries: {edge_stats['total_summaries']:,}")
        print(f"Total Consolidation Edges: {edge_stats['total_consolidation_edges']:,}")

        if edge_stats["edge_types"]:
            print("\nEdge Types from Summaries:")
            for edge_type, count in sorted(edge_stats["edge_types"].items(), key=lambda x: x[1], reverse=True):
                print(f"  {edge_type:<30} {count:>8,}")

        print(f"\nAverage Edges per Node: {edge_stats['average_edges_per_node']:.2f}")
        print(f"Overall Edge Coverage: {edge_stats['edge_coverage']:.1f}%")

        if edge_stats["periods_with_no_edges"]:
            print(f"\n⚠️  WARNING: {len(edge_stats['periods_with_no_edges'])} periods have NO edges!")
            for period in edge_stats["periods_with_no_edges"][:3]:
                print(f"  - {period}")
            if len(edge_stats["periods_with_no_edges"]) > 3:
                print(f"  ... and {len(edge_stats['periods_with_no_edges']) - 3} more")

        # Orphaned nodes analysis
        orphaned = self.get_orphaned_nodes_analysis()

        if orphaned["total_orphaned"] > 0:
            formatter.print_subsection("⚠️  ORPHANED NODES IN CONSOLIDATED PERIODS")
            print(f"Total Orphaned Nodes: {orphaned['total_orphaned']:,}")

            print("\nOrphaned by Type:")
            for node_type, count in sorted(orphaned["by_type"].items(), key=lambda x: x[1], reverse=True):
                print(f"  {node_type}: {count}")

            print("\nSample Periods with Orphaned Nodes:")
            for period, data in list(orphaned["by_period"].items())[:3]:
                print(f"\n{period}:")
                print(f"  Summary ID: {data['summary_id']}")
                print(f"  Orphaned Count: {data['count']}")
                for node in data["nodes"]:
                    print(f"    - {node['id']} ({node['type']})")

        # Growth analysis
        formatter.print_subsection("Storage Growth Analysis")

        if storage_stats.get("last_24_hours") and storage_stats.get("last_week"):
            daily_nodes = storage_stats["last_24_hours"]["nodes"]
            weekly_nodes = storage_stats["last_week"]["nodes"]

            if weekly_nodes > 0:
                daily_rate = daily_nodes
                weekly_avg = weekly_nodes / 7
                print(f"Daily Growth Rate: {daily_rate:,} nodes/day")
                print(f"Weekly Average: {weekly_avg:,.0f} nodes/day")

                # Project monthly growth
                monthly_projection = daily_rate * 30
                monthly_size_mb = (monthly_projection * 1024) / (1024 * 1024)  # Rough estimate
                print("\nProjected Monthly Growth:")
                print(f"  Nodes: {monthly_projection:,}")
                print(f"  Size: ~{monthly_size_mb:.1f} MB")

        # Recommendations
        if orphaned.get("recommendations"):
            formatter.print_subsection("Recommendations")
            for rec in orphaned["recommendations"]:
                print(f"\n[{rec['severity']}] {rec['issue']}")
                print(f"  Action: {rec['action']}")
