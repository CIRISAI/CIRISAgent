"""
TSDB-specific analysis functionality.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict

from .base import BaseDBTool, ReportFormatter


class TSDBAnalyzer(BaseDBTool):
    """Analyzer for TSDB consolidation data."""

    def get_tsdb_status(self) -> Dict[str, Any]:
        """Get comprehensive TSDB consolidation status."""
        status = {
            "consolidation_summaries": defaultdict(int),
            "last_consolidations": {},
            "data_coverage": {},
            "timeline_view": {},
            "resource_aggregation": {},
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Count consolidation summaries by level
            cursor.execute(
                """
                SELECT
                    json_extract(attributes_json, '$.consolidation_level') as level,
                    COUNT(*) as count
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                GROUP BY level
            """
            )

            for row in cursor:
                level = row["level"] or "basic"
                status["consolidation_summaries"][level] = row["count"]

            # Get last consolidation times for each level
            for level in ["basic", "extensive", "profound"]:
                cursor.execute(
                    """
                    SELECT
                        MAX(created_at) as last_run,
                        json_extract(attributes_json, '$.period_start') as period_start,
                        json_extract(attributes_json, '$.period_end') as period_end,
                        json_extract(attributes_json, '$.period_label') as period_label
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                      AND (json_extract(attributes_json, '$.consolidation_level') = ?
                           OR (? = 'basic' AND json_extract(attributes_json, '$.consolidation_level') IS NULL))
                """,
                    (level, level),
                )

                row = cursor.fetchone()
                if row and row["last_run"]:
                    status["last_consolidations"][level] = {
                        "last_run": row["last_run"],
                        "period_start": row["period_start"],
                        "period_end": row["period_end"],
                        "period_label": row["period_label"],
                    }

            # Get metrics data coverage
            cursor.execute(
                """
                SELECT
                    DATE(created_at) as date,
                    COUNT(*) as tsdb_nodes,
                    SUM(json_extract(attributes_json, '$.value')) as total_value
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                GROUP BY DATE(created_at)
                ORDER BY date DESC
                LIMIT 30
            """
            )

            status["data_coverage"]["by_date"] = []
            for row in cursor:
                status["data_coverage"]["by_date"].append(
                    {"date": row["date"], "node_count": row["tsdb_nodes"], "total_value": row["total_value"] or 0}
                )

            # Get top metrics
            cursor.execute(
                """
                SELECT
                    json_extract(attributes_json, '$.metric_name') as metric,
                    COUNT(*) as count
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                  AND datetime(created_at) >= datetime('now', '-7 days')
                GROUP BY metric
                ORDER BY count DESC
                LIMIT 10
            """
            )

            status["data_coverage"]["top_metrics"] = []
            for row in cursor:
                if row["metric"]:
                    status["data_coverage"]["top_metrics"].append({"metric": row["metric"], "count": row["count"]})

        return status

    def get_node_age_analysis(self) -> Dict[str, Any]:
        """Analyze TSDB data nodes by age to identify consolidation issues."""
        result = {
            "tsdb_data_nodes": {"within_30h": 0, "between_30_36h": 0, "over_36h": 0, "total": 0},
            "basic_summaries": {"within_7d": 0, "over_7d": 0, "over_15d": 0, "total": 0},
            "oldest_unconsolidated": None,
            "recommendations": [],
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Analyze TSDB data nodes by age
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) * 24 <= 30 THEN 1 END) as within_30h,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) * 24 > 30
                                AND (julianday('now') - julianday(created_at)) * 24 <= 36 THEN 1 END) as between_30_36h,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) * 24 > 36 THEN 1 END) as over_36h,
                    MIN(created_at) as oldest
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
            """
            )

            row = cursor.fetchone()
            if row:
                result["tsdb_data_nodes"] = {
                    "total": row["total"],
                    "within_30h": row["within_30h"],
                    "between_30_36h": row["between_30_36h"],
                    "over_36h": row["over_36h"],
                }

                if row["oldest"]:
                    result["oldest_unconsolidated"] = row["oldest"]

            # Analyze basic summaries by age
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) <= 7 THEN 1 END) as within_7d,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) > 7
                                AND (julianday('now') - julianday(created_at)) <= 15 THEN 1 END) as over_7d,
                    COUNT(CASE WHEN (julianday('now') - julianday(created_at)) > 15 THEN 1 END) as over_15d
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                  AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
            """
            )

            row = cursor.fetchone()
            if row:
                result["basic_summaries"] = {
                    "total": row["total"],
                    "within_7d": row["within_7d"],
                    "over_7d": row["over_7d"] - row["over_15d"],
                    "over_15d": row["over_15d"],
                }

            # Generate recommendations
            self._generate_recommendations(result)

        return result

    def _generate_recommendations(self, analysis: Dict[str, Any]):
        """Generate recommendations based on analysis."""
        if analysis["tsdb_data_nodes"]["over_36h"] > 0:
            analysis["recommendations"].append(
                {
                    "severity": "HIGH",
                    "issue": f"{analysis['tsdb_data_nodes']['over_36h']:,} TSDB data nodes older than 36 hours",
                    "action": "Check if consolidation service is running properly",
                }
            )

        if analysis["tsdb_data_nodes"]["between_30_36h"] > 100:
            analysis["recommendations"].append(
                {
                    "severity": "MEDIUM",
                    "issue": f"{analysis['tsdb_data_nodes']['between_30_36h']:,} nodes waiting for consolidation",
                    "action": "Normal if consolidation is about to run",
                }
            )

        if analysis["basic_summaries"]["over_7d"] > 0:
            analysis["recommendations"].append(
                {
                    "severity": "MEDIUM",
                    "issue": f"{analysis['basic_summaries']['over_7d']:,} basic summaries older than 7 days",
                    "action": "Should be consolidated to daily summaries",
                }
            )

        if analysis["basic_summaries"]["over_15d"] > 0:
            analysis["recommendations"].append(
                {
                    "severity": "HIGH",
                    "issue": f"{analysis['basic_summaries']['over_15d']:,} basic summaries older than 15 days",
                    "action": "Extensive consolidation may not be running",
                }
            )

    def print_report(self):
        """Print TSDB consolidation report."""
        formatter = ReportFormatter()
        formatter.print_section("TSDB CONSOLIDATION STATUS")

        status = self.get_tsdb_status()

        # Summary counts
        formatter.print_subsection("Consolidation Summaries")
        total = sum(status["consolidation_summaries"].values())
        print(f"Total Summaries: {total}")

        for level in ["basic", "extensive", "profound"]:
            count = status["consolidation_summaries"].get(level, 0)
            print(f"  {level.capitalize()}: {count}")

        # Last runs
        formatter.print_subsection("Last Consolidation Runs")
        for level in ["basic", "extensive", "profound"]:
            if level in status["last_consolidations"]:
                info = status["last_consolidations"][level]
                last_run = self.parse_timestamp(info["last_run"])
                age = datetime.now(timezone.utc) - last_run

                print(f"\n{level.capitalize()} Consolidation:")
                print(f"  Last Run: {last_run.strftime('%Y-%m-%d %H:%M:%S UTC')} ({self.format_timedelta(age)} ago)")
                print(f"  Period: {info['period_label']}")
            else:
                print(f"\n{level.capitalize()} Consolidation: NEVER RUN")

        # Age analysis
        age_analysis = self.get_node_age_analysis()
        formatter.print_subsection("TSDB Data Node Ages")

        tsdb_nodes = age_analysis["tsdb_data_nodes"]
        print(f"Total TSDB Data Nodes: {tsdb_nodes['total']:,}")
        print(f"  Within 30 hours (expected): {tsdb_nodes['within_30h']:,}")
        print(f"  30-36 hours (pending): {tsdb_nodes['between_30_36h']:,}")
        print(f"  Over 36 hours (overdue): {tsdb_nodes['over_36h']:,}")

        if age_analysis["recommendations"]:
            formatter.print_subsection("Recommendations")
            for rec in age_analysis["recommendations"]:
                print(f"\n[{rec['severity']}] {rec['issue']}")
                print(f"  Action: {rec['action']}")
