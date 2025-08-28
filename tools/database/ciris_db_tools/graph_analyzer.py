"""
Graph analysis functionality for nodes and edges.
"""

from typing import Any, Dict

from .base import BaseDBTool, ReportFormatter


class GraphAnalyzer(BaseDBTool):
    """Analyzer for graph nodes and edges."""

    def get_orphaned_nodes(self, limit: int = 100) -> Dict[str, Any]:
        """Get nodes that have no edges (orphaned nodes)."""
        result = {"total_orphaned": 0, "by_type": {}, "sample_nodes": [], "analysis": {}}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Count total nodes without edges
            cursor.execute(
                """
                SELECT COUNT(DISTINCT n.node_id) as orphaned_count
                FROM graph_nodes n
                LEFT JOIN graph_edges e1 ON n.node_id = e1.source_node_id
                LEFT JOIN graph_edges e2 ON n.node_id = e2.target_node_id
                WHERE e1.edge_id IS NULL AND e2.edge_id IS NULL
            """
            )

            result["total_orphaned"] = cursor.fetchone()["orphaned_count"]

            # Break down by node type
            cursor.execute(
                """
                SELECT n.node_type, COUNT(*) as count
                FROM graph_nodes n
                LEFT JOIN graph_edges e1 ON n.node_id = e1.source_node_id
                LEFT JOIN graph_edges e2 ON n.node_id = e2.target_node_id
                WHERE e1.edge_id IS NULL AND e2.edge_id IS NULL
                GROUP BY n.node_type
                ORDER BY count DESC
            """
            )

            for row in cursor:
                result["by_type"][row["node_type"]] = row["count"]

            # Get sample of orphaned nodes
            cursor.execute(
                f"""
                SELECT n.node_id, n.node_type, n.created_at, n.updated_at
                FROM graph_nodes n
                LEFT JOIN graph_edges e1 ON n.node_id = e1.source_node_id
                LEFT JOIN graph_edges e2 ON n.node_id = e2.target_node_id
                WHERE e1.edge_id IS NULL AND e2.edge_id IS NULL
                ORDER BY n.created_at DESC
                LIMIT {limit}
            """
            )

            for row in cursor:
                result["sample_nodes"].append(
                    {
                        "node_id": row["node_id"],
                        "node_type": row["node_type"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                )

            # Age analysis
            cursor.execute(
                """
                SELECT
                    COUNT(CASE WHEN datetime(n.created_at) > datetime('now', '-1 hour') THEN 1 END) as last_hour,
                    COUNT(CASE WHEN datetime(n.created_at) > datetime('now', '-6 hours') THEN 1 END) as last_6h,
                    COUNT(CASE WHEN datetime(n.created_at) > datetime('now', '-24 hours') THEN 1 END) as last_24h,
                    COUNT(CASE WHEN datetime(n.created_at) > datetime('now', '-7 days') THEN 1 END) as last_7d
                FROM graph_nodes n
                LEFT JOIN graph_edges e1 ON n.node_id = e1.source_node_id
                LEFT JOIN graph_edges e2 ON n.node_id = e2.target_node_id
                WHERE e1.edge_id IS NULL AND e2.edge_id IS NULL
            """
            )

            age_stats = cursor.fetchone()
            result["analysis"]["age_distribution"] = {
                "last_hour": age_stats["last_hour"],
                "last_6_hours": age_stats["last_6h"],
                "last_24_hours": age_stats["last_24h"],
                "last_7_days": age_stats["last_7d"],
            }

        return result

    def get_edge_statistics(self) -> Dict[str, Any]:
        """Get statistics about graph edges."""
        stats = {"total_edges": 0, "by_relationship": {}, "by_scope": {}, "orphaned_edges": 0, "duplicate_edges": 0}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total edges
            cursor.execute("SELECT COUNT(*) as count FROM graph_edges")
            stats["total_edges"] = cursor.fetchone()["count"]

            # By relationship type
            cursor.execute(
                """
                SELECT relationship, COUNT(*) as count
                FROM graph_edges
                GROUP BY relationship
                ORDER BY count DESC
            """
            )

            for row in cursor:
                stats["by_relationship"][row["relationship"]] = row["count"]

            # By scope
            cursor.execute(
                """
                SELECT scope, COUNT(*) as count
                FROM graph_edges
                GROUP BY scope
                ORDER BY count DESC
            """
            )

            for row in cursor:
                stats["by_scope"][row["scope"]] = row["count"]

            # Check for orphaned edges (edges pointing to non-existent nodes)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_edges e
                WHERE NOT EXISTS (SELECT 1 FROM graph_nodes WHERE node_id = e.source_node_id)
                   OR NOT EXISTS (SELECT 1 FROM graph_nodes WHERE node_id = e.target_node_id)
            """
            )
            stats["orphaned_edges"] = cursor.fetchone()["count"]

            # Check for duplicate edges
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM (
                    SELECT source_node_id, target_node_id, relationship, COUNT(*) as cnt
                    FROM graph_edges
                    GROUP BY source_node_id, target_node_id, relationship
                    HAVING cnt > 1
                )
            """
            )
            stats["duplicate_edges"] = cursor.fetchone()["count"]

        return stats

    def get_connectivity_report(self) -> Dict[str, Any]:
        """Get graph connectivity report."""
        report = {
            "total_nodes": 0,
            "connected_nodes": 0,
            "orphaned_nodes": 0,
            "connectivity_rate": 0.0,
            "avg_edges_per_node": 0.0,
            "most_connected": [],
            "least_connected": [],
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total nodes
            cursor.execute("SELECT COUNT(*) as count FROM graph_nodes")
            report["total_nodes"] = cursor.fetchone()["count"]

            # Connected nodes
            cursor.execute(
                """
                SELECT COUNT(DISTINCT node_id) as count
                FROM (
                    SELECT source_node_id as node_id FROM graph_edges
                    UNION
                    SELECT target_node_id as node_id FROM graph_edges
                )
            """
            )
            report["connected_nodes"] = cursor.fetchone()["count"]

            report["orphaned_nodes"] = report["total_nodes"] - report["connected_nodes"]

            if report["total_nodes"] > 0:
                report["connectivity_rate"] = (report["connected_nodes"] / report["total_nodes"]) * 100

            # Average edges per node
            cursor.execute(
                """
                SELECT AVG(edge_count) as avg_edges
                FROM (
                    SELECT node_id, COUNT(*) as edge_count
                    FROM (
                        SELECT source_node_id as node_id FROM graph_edges
                        UNION ALL
                        SELECT target_node_id as node_id FROM graph_edges
                    )
                    GROUP BY node_id
                )
            """
            )
            avg = cursor.fetchone()["avg_edges"]
            report["avg_edges_per_node"] = avg if avg else 0.0

            # Most connected nodes
            cursor.execute(
                """
                SELECT node_id, node_type, edge_count
                FROM (
                    SELECT n.node_id, n.node_type,
                           (SELECT COUNT(*) FROM graph_edges WHERE source_node_id = n.node_id OR target_node_id = n.node_id) as edge_count
                    FROM graph_nodes n
                )
                WHERE edge_count > 0
                ORDER BY edge_count DESC
                LIMIT 10
            """
            )

            for row in cursor:
                report["most_connected"].append(
                    {"node_id": row["node_id"], "node_type": row["node_type"], "edge_count": row["edge_count"]}
                )

        return report

    def print_orphaned_nodes_report(self):
        """Print report on orphaned nodes."""
        formatter = ReportFormatter()
        formatter.print_section("NODES WITHOUT EDGES (ORPHANED)")

        orphaned = self.get_orphaned_nodes()

        print(f"\nTotal Orphaned Nodes: {orphaned['total_orphaned']:,}")

        if orphaned["by_type"]:
            formatter.print_subsection("Orphaned Nodes by Type")
            for node_type, count in orphaned["by_type"].items():
                print(f"  {node_type}: {count:,}")

        if orphaned["analysis"]["age_distribution"]:
            formatter.print_subsection("Age Distribution")
            age = orphaned["analysis"]["age_distribution"]
            print(f"  Created in last hour: {age['last_hour']:,}")
            print(f"  Created in last 6 hours: {age['last_6_hours']:,}")
            print(f"  Created in last 24 hours: {age['last_24_hours']:,}")
            print(f"  Created in last 7 days: {age['last_7_days']:,}")

        if orphaned["sample_nodes"]:
            formatter.print_subsection("Sample Orphaned Nodes (newest first)")

            headers = ["Node ID", "Type", "Created"]
            rows = []
            for node in orphaned["sample_nodes"][:20]:
                created = node["created_at"][:19] if node["created_at"] else "Unknown"
                rows.append([node["node_id"][:35], node["node_type"], created])

            print("\n" + formatter.format_table(headers, rows, [35, 15, 20]))

    def print_connectivity_report(self):
        """Print graph connectivity report."""
        formatter = ReportFormatter()
        formatter.print_section("GRAPH CONNECTIVITY ANALYSIS")

        report = self.get_connectivity_report()

        formatter.print_subsection("Overall Connectivity")
        print(f"Total Nodes: {report['total_nodes']:,}")
        print(f"Connected Nodes: {report['connected_nodes']:,}")
        print(f"Orphaned Nodes: {report['orphaned_nodes']:,}")
        print(f"Connectivity Rate: {report['connectivity_rate']:.1f}%")
        print(f"Average Edges per Node: {report['avg_edges_per_node']:.1f}")

        edge_stats = self.get_edge_statistics()

        formatter.print_subsection("Edge Statistics")
        print(f"Total Edges: {edge_stats['total_edges']:,}")
        print(f"Orphaned Edges: {edge_stats['orphaned_edges']:,}")
        print(f"Duplicate Edges: {edge_stats['duplicate_edges']:,}")

        if edge_stats["by_relationship"]:
            print("\nEdges by Relationship:")
            for rel, count in list(edge_stats["by_relationship"].items())[:10]:
                print(f"  {rel}: {count:,}")

        if report["most_connected"]:
            formatter.print_subsection("Most Connected Nodes")
            headers = ["Node ID", "Type", "Edge Count"]
            rows = []
            for node in report["most_connected"]:
                rows.append([node["node_id"][:40], node["node_type"], f"{node['edge_count']:,}"])

            print("\n" + formatter.format_table(headers, rows, [40, 15, 12]))
