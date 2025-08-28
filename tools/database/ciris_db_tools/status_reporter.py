"""
Database status reporting functionality.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .base import BaseDBTool, ReportFormatter


class DBStatusReporter(BaseDBTool):
    """Comprehensive database status reporting."""

    def get_overall_status(self) -> Dict[str, Any]:
        """Get overall database status including file info and basic stats."""
        status = {"main_db": {}, "audit_db": {}, "graph_nodes": {}, "correlations": {}, "tasks": {}, "thoughts": {}}

        # Main database info
        if Path(self.db_path).exists():
            stat = Path(self.db_path).stat()
            status["main_db"] = {
                "exists": True,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            }
        else:
            status["main_db"]["exists"] = False

        # Audit database info
        if Path(self.audit_db_path).exists():
            stat = Path(self.audit_db_path).stat()
            status["audit_db"] = {"exists": True, "size": stat.st_size}

            # Get audit entry count
            try:
                with self.get_connection(str(self.audit_db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*), MIN(sequence_number), MAX(sequence_number) FROM audit_log")
                    row = cursor.fetchone()
                    if row:
                        status["audit_db"]["entries"] = row[0]
                        status["audit_db"]["sequence_range"] = (row[1], row[2])
            except Exception:
                pass
        else:
            status["audit_db"]["exists"] = False

        # Get main database stats
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Graph nodes summary
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        MIN(created_at) as oldest,
                        MAX(created_at) as newest
                    FROM graph_nodes
                """
                )
                row = cursor.fetchone()
                if row:
                    status["graph_nodes"] = {"total": row["total"], "oldest": row["oldest"], "newest": row["newest"]}

                # Nodes by type
                cursor.execute(
                    """
                    SELECT node_type, COUNT(*) as count
                    FROM graph_nodes
                    GROUP BY node_type
                    ORDER BY count DESC
                """
                )
                status["graph_nodes"]["by_type"] = {}
                for row in cursor:
                    status["graph_nodes"]["by_type"][row["node_type"]] = row["count"]

                # Service correlations
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT correlation_type) as types
                    FROM service_correlations
                """
                )
                row = cursor.fetchone()
                if row:
                    status["correlations"]["total"] = row["total"]
                    status["correlations"]["types"] = row["types"]

                # Correlations by type
                cursor.execute(
                    """
                    SELECT correlation_type, COUNT(*) as count
                    FROM service_correlations
                    GROUP BY correlation_type
                    ORDER BY count DESC
                """
                )
                status["correlations"]["by_type"] = {}
                for row in cursor:
                    status["correlations"]["by_type"][row["correlation_type"]] = row["count"]

                # Tasks summary
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT status) as statuses
                    FROM tasks
                """
                )
                row = cursor.fetchone()
                if row:
                    status["tasks"]["total"] = row["total"]

                # Tasks by status
                cursor.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM tasks
                    GROUP BY status
                    ORDER BY count DESC
                """
                )
                status["tasks"]["by_status"] = {}
                for row in cursor:
                    status["tasks"]["by_status"][row["status"]] = row["count"]

                # Thoughts summary
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT status) as statuses
                    FROM thoughts
                """
                )
                row = cursor.fetchone()
                if row:
                    status["thoughts"]["total"] = row["total"]

                # Thoughts by status
                cursor.execute(
                    """
                    SELECT status, COUNT(*) as count
                    FROM thoughts
                    GROUP BY status
                    ORDER BY count DESC
                """
                )
                status["thoughts"]["by_status"] = {}
                for row in cursor:
                    status["thoughts"]["by_status"][row["status"]] = row["count"]

        except Exception as e:
            status["error"] = str(e)

        return status

    def print_full_report(self):
        """Print comprehensive status report."""
        formatter = ReportFormatter()
        formatter.print_section("CIRIS DATABASE STATUS REPORT")

        status = self.get_overall_status()

        # Database files
        formatter.print_subsection("Database Files")

        if status["main_db"].get("exists"):
            print(f"Main DB: {self.db_path}")
            print(f"  Size: {self.format_size(status['main_db']['size'])}")
            print(f"  Modified: {status['main_db']['modified'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print(f"Main DB: NOT FOUND at {self.db_path}")

        if status["audit_db"].get("exists"):
            print(f"\nAudit DB: {self.audit_db_path}")
            print(f"  Size: {self.format_size(status['audit_db']['size'])}")
            if "entries" in status["audit_db"]:
                print(f"  Entries: {status['audit_db']['entries']:,}")
                if "sequence_range" in status["audit_db"]:
                    seq_min, seq_max = status["audit_db"]["sequence_range"]
                    print(f"  Sequence Range: {seq_min:,} - {seq_max:,}")
        else:
            print(f"\nAudit DB: NOT FOUND at {self.audit_db_path}")

        # Graph nodes
        if status["graph_nodes"].get("total"):
            formatter.print_subsection("Graph Nodes")
            print(f"Total Nodes: {status['graph_nodes']['total']:,}")

            if status["graph_nodes"].get("oldest"):
                oldest = self.parse_timestamp(status["graph_nodes"]["oldest"])
                newest = self.parse_timestamp(status["graph_nodes"]["newest"])
                age = datetime.now(timezone.utc) - oldest

                print(f"Date Range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
                print(f"Data Age: {self.format_timedelta(age)}")

            if status["graph_nodes"].get("by_type"):
                print("\nNodes by Type:")
                for node_type, count in status["graph_nodes"]["by_type"].items():
                    print(f"  {node_type}: {count:,}")

        # Service correlations
        if status["correlations"].get("total"):
            formatter.print_subsection("Service Correlations")
            print(f"Total Correlations: {status['correlations']['total']:,}")

            if status["correlations"].get("by_type"):
                print("\nBy Type:")
                for corr_type, count in status["correlations"]["by_type"].items():
                    print(f"  {corr_type}: {count:,}")

        # Tasks and thoughts
        if status["tasks"].get("total") or status["thoughts"].get("total"):
            formatter.print_subsection("Tasks and Thoughts")

            if status["tasks"].get("total"):
                print(f"Total Tasks: {status['tasks']['total']:,}")
                if status["tasks"].get("by_status"):
                    for task_status, count in status["tasks"]["by_status"].items():
                        print(f"  {task_status}: {count:,}")

            if status["thoughts"].get("total"):
                print(f"\nTotal Thoughts: {status['thoughts']['total']:,}")
                if status["thoughts"].get("by_status"):
                    for thought_status, count in status["thoughts"]["by_status"].items():
                        print(f"  {thought_status}: {count:,}")

        if status.get("error"):
            print(f"\nERROR: {status['error']}")
