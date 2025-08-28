"""
Monitor and analyze consolidation state.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from .base import BaseDBTool, ReportFormatter
from .storage_analyzer import StorageAnalyzer


class ConsolidationMonitor(BaseDBTool):
    """Monitor consolidation progress and health."""

    def get_consolidation_gaps(self) -> Dict[str, Any]:
        """Find gaps in consolidation coverage."""
        gaps = {
            "basic_gaps": [],
            "extensive_gaps": [],
            "profound_gaps": [],
            "expected_vs_actual": {},
            "recommendations": [],
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Find the data range
            cursor.execute(
                """
                SELECT
                    MIN(created_at) as oldest,
                    MAX(created_at) as newest
                FROM graph_nodes
                WHERE node_type IN ('tsdb_data', 'audit_entry', 'concept', 'observation')
            """
            )

            row = cursor.fetchone()
            if not row or not row["oldest"]:
                return gaps

            oldest = self.parse_timestamp(row["oldest"])
            newest = self.parse_timestamp(row["newest"])

            # Calculate expected consolidations
            data_age = (newest - oldest).total_seconds() / 3600  # Hours

            # Basic (6-hour)
            expected_basic = int(data_age / 6)
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                  AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
            """
            )
            actual_basic = cursor.fetchone()["count"]

            gaps["expected_vs_actual"]["basic"] = {
                "expected": expected_basic,
                "actual": actual_basic,
                "coverage": (actual_basic / expected_basic * 100) if expected_basic > 0 else 0,
            }

            # Find specific gaps in basic consolidation
            self._find_basic_gaps(cursor, oldest, newest, gaps)

            # Extensive (daily)
            if data_age >= 168:  # 7 days
                expected_extensive = int(data_age / 24)
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                      AND json_extract(attributes_json, '$.consolidation_level') = 'extensive'
                """
                )
                actual_extensive = cursor.fetchone()["count"]

                gaps["expected_vs_actual"]["extensive"] = {
                    "expected": expected_extensive,
                    "actual": actual_extensive,
                    "coverage": (actual_extensive / expected_extensive * 100) if expected_extensive > 0 else 0,
                }

            # Generate recommendations
            self._generate_gap_recommendations(gaps)

        return gaps

    def _find_basic_gaps(self, cursor, oldest: datetime, newest: datetime, gaps: Dict):
        """Find specific gaps in basic consolidation."""
        # Get all basic consolidation periods
        cursor.execute(
            """
            SELECT
                json_extract(attributes_json, '$.period_start') as period_start,
                json_extract(attributes_json, '$.period_end') as period_end
            FROM graph_nodes
            WHERE node_type = 'tsdb_summary'
              AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
            ORDER BY period_start
        """
        )

        consolidated_periods = []
        for row in cursor:
            if row["period_start"] and row["period_end"]:
                start = self.parse_timestamp(row["period_start"])
                end = self.parse_timestamp(row["period_end"])
                consolidated_periods.append((start, end))

        # Find gaps
        current = oldest.replace(hour=(oldest.hour // 6) * 6, minute=0, second=0, microsecond=0)
        cutoff = newest - timedelta(hours=30)  # Don't report gaps in last 30 hours

        while current < cutoff:
            period_end = current + timedelta(hours=6)

            # Check if this period is consolidated
            is_consolidated = any(start <= current < end for start, end in consolidated_periods)

            if not is_consolidated:
                # Check if there's data in this period
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM graph_nodes
                    WHERE node_type IN ('tsdb_data', 'audit_entry', 'concept')
                      AND datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                """,
                    (current.isoformat(), period_end.isoformat()),
                )

                if cursor.fetchone()["count"] > 0:
                    gaps["basic_gaps"].append(
                        {
                            "period_start": current.isoformat(),
                            "period_end": period_end.isoformat(),
                            "age": self.format_timedelta(datetime.now(timezone.utc) - current),
                        }
                    )

            current = period_end

    def _generate_gap_recommendations(self, gaps: Dict):
        """Generate recommendations based on gaps."""
        if gaps["basic_gaps"]:
            gaps["recommendations"].append(
                {
                    "severity": "HIGH",
                    "issue": f"{len(gaps['basic_gaps'])} missing basic consolidation periods",
                    "action": "Run catch-up consolidation for missed periods",
                }
            )

        basic_coverage = gaps["expected_vs_actual"].get("basic", {}).get("coverage", 100)
        if basic_coverage < 80:
            gaps["recommendations"].append(
                {
                    "severity": "MEDIUM",
                    "issue": f"Basic consolidation coverage only {basic_coverage:.1f}%",
                    "action": "Check consolidation service health and scheduling",
                }
            )

    def get_retention_analysis(self) -> Dict[str, Any]:
        """Analyze data retention and cleanup effectiveness."""
        analysis = {
            "raw_data": {"total": 0, "should_be_cleaned": 0, "oldest": None},
            "basic_summaries": {"total": 0, "should_be_consolidated": 0, "oldest": None},
            "storage_estimate": {"current_size_mb": 0, "optimal_size_mb": 0, "savings_potential_mb": 0},
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Raw data analysis
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN datetime(created_at) < datetime('now', '-24 hours') THEN 1 END) as old_count,
                    MIN(created_at) as oldest
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
            """
            )

            row = cursor.fetchone()
            if row:
                analysis["raw_data"]["total"] = row["total"]
                analysis["raw_data"]["should_be_cleaned"] = row["old_count"]
                analysis["raw_data"]["oldest"] = row["oldest"]

            # Basic summaries analysis
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN datetime(created_at) < datetime('now', '-7 days') THEN 1 END) as old_count,
                    MIN(created_at) as oldest
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                  AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
            """
            )

            row = cursor.fetchone()
            if row:
                analysis["basic_summaries"]["total"] = row["total"]
                analysis["basic_summaries"]["should_be_consolidated"] = row["old_count"]
                analysis["basic_summaries"]["oldest"] = row["oldest"]

            # Storage estimate (rough)
            # Assume each node is ~1KB on average
            total_nodes = analysis["raw_data"]["total"] + analysis["basic_summaries"]["total"]
            deletable_nodes = (
                analysis["raw_data"]["should_be_cleaned"] + analysis["basic_summaries"]["should_be_consolidated"]
            )

            analysis["storage_estimate"]["current_size_mb"] = (total_nodes * 1024) / (1024 * 1024)
            analysis["storage_estimate"]["optimal_size_mb"] = ((total_nodes - deletable_nodes) * 1024) / (1024 * 1024)
            analysis["storage_estimate"]["savings_potential_mb"] = (
                analysis["storage_estimate"]["current_size_mb"] - analysis["storage_estimate"]["optimal_size_mb"]
            )

        return analysis

    def get_consolidation_health(self) -> Dict[str, Any]:
        """Get overall consolidation health metrics."""
        health = {
            "last_basic_run": None,
            "last_extensive_run": None,
            "last_profound_run": None,
            "basic_interval_health": "UNKNOWN",
            "extensive_interval_health": "UNKNOWN",
            "profound_interval_health": "UNKNOWN",
            "overall_health_score": 0.0,
            "basic_coverage": 0.0,
            "extensive_coverage": 0.0,
            "profound_coverage": 0.0,
            "orphaned_nodes_issue": False,
        }

        # Implementation would calculate these metrics
        gaps = self.get_consolidation_gaps()
        health["basic_coverage"] = gaps["expected_vs_actual"].get("basic", {}).get("coverage", 0)
        health["overall_health_score"] = health["basic_coverage"]

        return health

    def get_orphaned_nodes_in_consolidated_periods(self) -> Dict[str, Any]:
        """Find nodes without edges in periods that have been consolidated."""
        result = {"orphaned_in_consolidated": [], "by_type": {}, "by_period": {}, "total_orphaned": 0}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # First, get all consolidated periods
            cursor.execute(
                """
                SELECT DISTINCT
                    json_extract(attributes_json, '$.period_start') as period_start,
                    json_extract(attributes_json, '$.period_end') as period_end,
                    node_id as summary_id
                FROM graph_nodes
                WHERE node_type = 'tsdb_summary'
                ORDER BY period_start DESC
            """
            )

            consolidated_periods = cursor.fetchall()

            for period in consolidated_periods:
                period_start = period["period_start"]
                period_end = period["period_end"]
                summary_id = period["summary_id"]

                # Find nodes created in this period without edges
                cursor.execute(
                    """
                    SELECT n.node_id, n.node_type, n.created_at
                    FROM graph_nodes n
                    LEFT JOIN graph_edges e1 ON n.node_id = e1.source_node_id
                    LEFT JOIN graph_edges e2 ON n.node_id = e2.target_node_id
                    WHERE e1.edge_id IS NULL AND e2.edge_id IS NULL
                      AND n.scope = 'local'
                      AND n.node_type != 'tsdb_data'  -- Skip temporary nodes
                      AND datetime(n.created_at) >= datetime(?)
                      AND datetime(n.created_at) < datetime(?)
                """,
                    (period_start, period_end),
                )

                orphaned = cursor.fetchall()
                if orphaned:
                    period_key = f"{period_start} to {period_end}"
                    result["by_period"][period_key] = {
                        "summary_id": summary_id,
                        "orphaned_count": len(orphaned),
                        "nodes": [],
                    }

                    for node in orphaned:
                        node_info = {
                            "node_id": node["node_id"],
                            "node_type": node["node_type"],
                            "created_at": node["created_at"],
                            "period": period_key,
                            "summary_id": summary_id,
                        }
                        result["orphaned_in_consolidated"].append(node_info)
                        result["by_period"][period_key]["nodes"].append(node_info)

                        # Count by type
                        node_type = node["node_type"]
                        if node_type not in result["by_type"]:
                            result["by_type"][node_type] = 0
                        result["by_type"][node_type] += 1

            result["total_orphaned"] = len(result["orphaned_in_consolidated"])

        return result

    def print_report(self):
        """Print consolidation monitoring report."""
        formatter = ReportFormatter()
        formatter.print_section("CONSOLIDATION MONITORING")

        gaps = self.get_consolidation_gaps()
        health = self.get_consolidation_health()

        # Check for orphaned nodes in consolidated periods
        orphaned = self.get_orphaned_nodes_in_consolidated_periods()
        if orphaned["total_orphaned"] > 0:
            print(f"\n⚠️  WARNING: {orphaned['total_orphaned']} nodes without edges in consolidated periods!")
            print("   Run 'consolidation --orphaned' for details")

        # Health overview
        formatter.print_subsection("Consolidation Health")
        print(f"Overall Health Score: {health['overall_health_score']:.1f}%")
        print("\nConsolidation Coverage:")
        print(f"  Basic: {health['basic_coverage']:.1f}%")
        print(f"  Extensive: {health.get('extensive_coverage', 0):.1f}%")
        print(f"  Profound: {health.get('profound_coverage', 0):.1f}%")

    def print_orphaned_nodes_report(self):
        """Print report on nodes without edges in consolidated periods."""
        formatter = ReportFormatter()
        formatter.print_section("ORPHANED NODES IN CONSOLIDATED PERIODS")

        orphaned = self.get_orphaned_nodes_in_consolidated_periods()

        if orphaned["total_orphaned"] == 0:
            print("✓ No orphaned nodes found in consolidated periods")
            return

        print(f"\n⚠️  Found {orphaned['total_orphaned']} nodes without edges in consolidated periods")

        if orphaned["by_type"]:
            formatter.print_subsection("Orphaned Nodes by Type")
            for node_type, count in orphaned["by_type"].items():
                print(f"  {node_type}: {count}")

        if orphaned["by_period"]:
            formatter.print_subsection("Orphaned Nodes by Period")
            for period, data in list(orphaned["by_period"].items())[:5]:
                print(f"\n{period}:")
                print(f"  Summary: {data['summary_id']}")
                print(f"  Orphaned nodes: {data['orphaned_count']}")

                # Show sample nodes
                for node in data["nodes"][:3]:
                    print(f"    - {node['node_id']} ({node['node_type']})")

                if len(data["nodes"]) > 3:
                    print(f"    ... and {len(data['nodes']) - 3} more")

            if len(orphaned["by_period"]) > 5:
                print(f"\n... and {len(orphaned['by_period']) - 5} more periods")

        print("\n⚠️  This indicates the SUMMARIZES edge creation is not working properly!")

    def print_consolidation_health_report(self):
        """Print comprehensive consolidation health report."""
        formatter = ReportFormatter()
        formatter.print_section("CONSOLIDATION HEALTH REPORT")

        # Gaps analysis
        gaps = self.get_consolidation_gaps()

        formatter.print_subsection("Consolidation Coverage")
        for level, stats in gaps["expected_vs_actual"].items():
            print(f"\n{level.capitalize()} Consolidation:")
            print(f"  Expected: {stats['expected']}")
            print(f"  Actual: {stats['actual']}")
            print(f"  Coverage: {stats['coverage']:.1f}%")

        if gaps["basic_gaps"]:
            formatter.print_subsection("Missing Basic Consolidation Periods")
            print(f"Found {len(gaps['basic_gaps'])} gaps:")
            for gap in gaps["basic_gaps"][:5]:
                start = self.parse_timestamp(gap["period_start"])
                print(f"  {start.strftime('%Y-%m-%d %H:%M')} - Age: {gap['age']}")
            if len(gaps["basic_gaps"]) > 5:
                print(f"  ... and {len(gaps['basic_gaps']) - 5} more")

        # Retention analysis
        retention = self.get_retention_analysis()

        formatter.print_subsection("Data Retention Status")

        if retention["raw_data"]["oldest"]:
            oldest = self.parse_timestamp(retention["raw_data"]["oldest"])
            age = datetime.now(timezone.utc) - oldest
            print("\nRaw TSDB Data:")
            print(f"  Total Nodes: {retention['raw_data']['total']:,}")
            print(f"  Should Be Cleaned: {retention['raw_data']['should_be_cleaned']:,}")
            print(f"  Oldest: {oldest.strftime('%Y-%m-%d %H:%M')} ({self.format_timedelta(age)} ago)")

        if retention["basic_summaries"]["oldest"]:
            oldest = self.parse_timestamp(retention["basic_summaries"]["oldest"])
            age = datetime.now(timezone.utc) - oldest
            print("\nBasic Summaries:")
            print(f"  Total: {retention['basic_summaries']['total']:,}")
            print(f"  Should Be Consolidated: {retention['basic_summaries']['should_be_consolidated']:,}")
            print(f"  Oldest: {oldest.strftime('%Y-%m-%d %H:%M')} ({self.format_timedelta(age)} ago)")

        print("\nStorage Estimate:")
        print(f"  Current Size: {retention['storage_estimate']['current_size_mb']:.1f} MB")
        print(f"  Optimal Size: {retention['storage_estimate']['optimal_size_mb']:.1f} MB")
        print(f"  Potential Savings: {retention['storage_estimate']['savings_potential_mb']:.1f} MB")

        # Recommendations
        if gaps["recommendations"]:
            formatter.print_subsection("Recommendations")
            for rec in gaps["recommendations"]:
                print(f"\n[{rec['severity']}] {rec['issue']}")
                print(f"  Action: {rec['action']}")

    def print_orphaned_consolidated_report(self):
        """Alias for print_orphaned_nodes_report."""
        self.print_orphaned_nodes_report()

    def print_comprehensive_analysis(self):
        """Print comprehensive analysis including orphaned nodes, storage, and edge statistics."""
        formatter = ReportFormatter()
        formatter.print_section("COMPREHENSIVE TSDB CONSOLIDATION ANALYSIS")

        # First check for critical issues
        orphaned = self.get_orphaned_nodes_in_consolidated_periods()

        if orphaned["total_orphaned"] > 0:
            print(f"\n🚨 CRITICAL: {orphaned['total_orphaned']} orphaned nodes found in consolidated periods!")
            print("   These nodes exist within the same scope as summaries but have no SUMMARIZES edges.")
            print("   This indicates the edge creation logic is not working properly.\n")

        # Storage analysis
        storage = StorageAnalyzer(db_path=self.db_path)
        storage_stats = storage.get_storage_by_time_period()

        formatter.print_subsection("Data Storage Statistics")

        print(f"{'Period':<20} {'Nodes':>12} {'Edges':>12} {'Size (MB)':>12}")
        print("-" * 58)

        for period, stats in storage_stats.items():
            period_label = period.replace("_", " ").title()
            print(f"{period_label:<20} {stats['nodes']:>12,} {stats['edges']:>12,} {stats['size_estimate_mb']:>12.2f}")

        # Edge statistics
        edge_stats = storage.get_edge_statistics_for_consolidated_periods()

        formatter.print_subsection("Consolidation Edge Statistics")
        if "total_summaries" in edge_stats:
            print(f"Total Summaries: {edge_stats['total_summaries']:,}")
        if "total_consolidation_edges" in edge_stats:
            print(f"Total Consolidation Edges: {edge_stats['total_consolidation_edges']:,}")
        print(f"Average Edges per Node: {edge_stats['average_edges_per_node']:.2f}")
        if "total_summarizes_edges" in edge_stats:
            print(f"Total SUMMARIZES Edges: {edge_stats['total_summarizes_edges']:,}")
        print(f"Edge Coverage: {edge_stats['edge_coverage']:.1f}%")

        if edge_stats["periods_with_no_edges"]:
            print(f"\n⚠️  {len(edge_stats['periods_with_no_edges'])} periods have NO edges")

        # Consolidation health
        gaps = self.get_consolidation_gaps()

        formatter.print_subsection("Consolidation Coverage")
        for level, stats in gaps["expected_vs_actual"].items():
            print(f"{level.capitalize()}: {stats['actual']}/{stats['expected']} ({stats['coverage']:.1f}%)")

        # Orphaned nodes details if any
        if orphaned["total_orphaned"] > 0:
            formatter.print_subsection("Orphaned Nodes Details")

            print("By Type:")
            for node_type, count in sorted(orphaned["by_type"].items(), key=lambda x: x[1], reverse=True):
                print(f"  {node_type}: {count}")

            print("\nSample Affected Periods:")
            for period, data in list(orphaned["by_period"].items())[:3]:
                print(f"  {period}: {data['orphaned_count']} orphaned nodes")

        # Recommendations
        all_recommendations = []

        if orphaned["total_orphaned"] > 0:
            all_recommendations.append(
                {
                    "severity": "CRITICAL",
                    "issue": f"{orphaned['total_orphaned']} orphaned nodes in consolidated periods",
                    "action": "Run edge recalculation for all affected periods immediately",
                }
            )

        if edge_stats["average_edges_per_node"] < 0.8:
            all_recommendations.append(
                {
                    "severity": "HIGH",
                    "issue": f"Low edge coverage ({edge_stats['average_edges_per_node']:.2f} edges/node)",
                    "action": "Investigate edge creation logic in consolidation service",
                }
            )

        all_recommendations.extend(gaps.get("recommendations", []))

        if all_recommendations:
            formatter.print_subsection("Recommendations")
            for rec in sorted(all_recommendations, key=lambda x: x["severity"], reverse=True):
                print(f"\n[{rec['severity']}] {rec['issue']}")
                print(f"  → {rec['action']}")
