#!/usr/bin/env python3
"""
CIRIS Database Status and Integrity Tool

Provides comprehensive reporting on:
- Database statistics and health
- TSDB consolidation status and history
- Audit trail integrity with cryptographic verification
- Graph node counts and metrics
- Data availability for testing

Usage:
    python db_status_tool.py [command]

Commands:
    status      - Overall database status (default)
    tsdb        - TSDB consolidation details
    audit       - Audit trail verification
    verify      - Full integrity verification
    periods     - Available data periods for testing
"""

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.audit.verifier import AuditVerifier
from ciris_engine.logic.config import get_sqlite_db_full_path


class DBStatusTool:
    """Database status and integrity reporting tool."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database connection."""
        self.db_path = db_path or get_sqlite_db_full_path()
        self.audit_db_path = Path(self.db_path).parent / "ciris_audit.db"

    def get_connection(self, db_path: Optional[str] = None) -> sqlite3.Connection:
        """Get database connection."""
        path = db_path or self.db_path
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def format_size(self, bytes: int) -> str:
        """Format bytes as human-readable size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} TB"

    def format_timedelta(self, td: timedelta) -> str:
        """Format timedelta as human-readable string."""
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    def print_section(self, title: str, width: int = 80):
        """Print a section header."""
        print("\n" + "=" * width)
        print(f" {title} ".center(width))
        print("=" * width)

    def print_subsection(self, title: str, width: int = 60):
        """Print a subsection header."""
        print(f"\n{title}")
        print("-" * len(title))

    def get_overall_status(self) -> Dict[str, Any]:
        """Get overall database status."""
        status = {"main_db": {}, "audit_db": {}, "graph_nodes": {}, "correlations": {}, "tasks": {}, "thoughts": {}}

        # Main database stats
        if Path(self.db_path).exists():
            status["main_db"]["exists"] = True
            status["main_db"]["size"] = Path(self.db_path).stat().st_size
            status["main_db"]["modified"] = datetime.fromtimestamp(Path(self.db_path).stat().st_mtime, tz=timezone.utc)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Graph nodes count by type
                cursor.execute(
                    """
                    SELECT node_type, COUNT(*) as count
                    FROM graph_nodes
                    GROUP BY node_type
                    ORDER BY count DESC
                """
                )
                status["graph_nodes"]["by_type"] = {row["node_type"]: row["count"] for row in cursor}
                status["graph_nodes"]["total"] = sum(status["graph_nodes"]["by_type"].values())

                # Get date range
                cursor.execute("SELECT MIN(created_at) as oldest, MAX(created_at) as newest FROM graph_nodes")
                row = cursor.fetchone()
                if row and row["oldest"]:
                    status["graph_nodes"]["oldest"] = row["oldest"]
                    status["graph_nodes"]["newest"] = row["newest"]

                # Service correlations
                cursor.execute("SELECT COUNT(*) as count FROM service_correlations")
                status["correlations"]["total"] = cursor.fetchone()["count"]

                cursor.execute(
                    """
                    SELECT correlation_type, COUNT(*) as count
                    FROM service_correlations
                    GROUP BY correlation_type
                """
                )
                status["correlations"]["by_type"] = {row["correlation_type"]: row["count"] for row in cursor}

                # Tasks
                cursor.execute("SELECT status, COUNT(*) as count FROM tasks GROUP BY status")
                status["tasks"]["by_status"] = {row["status"]: row["count"] for row in cursor}
                status["tasks"]["total"] = sum(status["tasks"]["by_status"].values())

                # Thoughts
                cursor.execute("SELECT status, COUNT(*) as count FROM thoughts GROUP BY status")
                status["thoughts"]["by_status"] = {row["status"]: row["count"] for row in cursor}
                status["thoughts"]["total"] = sum(status["thoughts"]["by_status"].values())
        else:
            status["main_db"]["exists"] = False

        # Audit database stats
        if Path(self.audit_db_path).exists():
            status["audit_db"]["exists"] = True
            status["audit_db"]["size"] = Path(self.audit_db_path).stat().st_size

            with self.get_connection(str(self.audit_db_path)) as conn:
                cursor = conn.cursor()

                # Audit entries
                cursor.execute("SELECT COUNT(*) as count FROM audit_log")
                status["audit_db"]["entries"] = cursor.fetchone()["count"]

                # Get sequence range
                cursor.execute("SELECT MIN(sequence_number) as min_seq, MAX(sequence_number) as max_seq FROM audit_log")
                row = cursor.fetchone()
                if row and row["min_seq"] is not None:
                    status["audit_db"]["sequence_range"] = (row["min_seq"], row["max_seq"])

                # Signing keys
                cursor.execute("SELECT COUNT(*) as total, COUNT(revoked_at) as revoked FROM audit_signing_keys")
                row = cursor.fetchone()
                status["audit_db"]["signing_keys"] = {
                    "total": row["total"],
                    "active": row["total"] - row["revoked"],
                    "revoked": row["revoked"],
                }
        else:
            status["audit_db"]["exists"] = False

        return status

    def get_tsdb_status(self) -> Dict[str, Any]:
        """Get TSDB consolidation status."""
        status = {
            "consolidation_summaries": {},
            "last_consolidations": {},
            "data_coverage": {},
            "metrics": {},
            "timeline_view": {},
            "edge_creation": {},
            "node_connectivity": {},
        }

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Count consolidation summaries
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

            status["data_coverage"]["daily_metrics"] = []
            for row in cursor:
                status["data_coverage"]["daily_metrics"].append(
                    {"date": row["date"], "node_count": row["tsdb_nodes"], "total_value": row["total_value"]}
                )

            # Get metric types
            cursor.execute(
                """
                SELECT
                    json_extract(attributes_json, '$.metric_name') as metric,
                    COUNT(*) as count
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                  AND created_at >= datetime('now', '-7 days')
                GROUP BY metric
                ORDER BY count DESC
                LIMIT 20
            """
            )

            status["metrics"]["top_metrics_7d"] = {row["metric"]: row["count"] for row in cursor if row["metric"]}

            # Check for gaps in consolidation
            cursor.execute(
                """
                WITH periods AS (
                    SELECT
                        json_extract(attributes_json, '$.period_start') as period_start,
                        json_extract(attributes_json, '$.period_end') as period_end,
                        json_extract(attributes_json, '$.consolidation_level') as level
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                      AND created_at >= datetime('now', '-30 days')
                    ORDER BY period_start
                )
                SELECT * FROM periods
            """
            )

            periods = list(cursor)
            if periods:
                # Check for gaps (simplified - just count expected vs actual)
                now = datetime.now(timezone.utc)
                thirty_days_ago = now - timedelta(days=30)

                # Expected basic consolidations (every 6 hours)
                expected_basic = int((now - thirty_days_ago).total_seconds() / (6 * 3600))
                actual_basic = sum(1 for p in periods if not p["level"] or p["level"] == "basic")

                status["data_coverage"]["consolidation_gaps"] = {
                    "expected_basic_30d": expected_basic,
                    "actual_basic_30d": actual_basic,
                    "coverage_percent": (actual_basic / expected_basic * 100) if expected_basic > 0 else 0,
                }

            # Timeline view - nodes grouped by the period they represent
            cursor.execute(
                """
                SELECT
                    DATE(json_extract(attributes_json, '$.period_start')) as period_date,
                    json_extract(attributes_json, '$.consolidation_level') as level,
                    COUNT(*) as count,
                    MIN(json_extract(attributes_json, '$.period_start')) as earliest,
                    MAX(json_extract(attributes_json, '$.period_end')) as latest
                FROM graph_nodes
                WHERE node_type IN ('tsdb_summary', 'audit_summary', 'trace_summary',
                                   'task_summary', 'conversation_summary')
                  AND json_extract(attributes_json, '$.period_start') IS NOT NULL
                GROUP BY period_date, level
                ORDER BY period_date DESC
                LIMIT 30
            """
            )

            timeline_data = defaultdict(lambda: {"basic": 0, "extensive": 0, "profound": 0})
            for row in cursor:
                if row["period_date"] and row["level"]:
                    timeline_data[row["period_date"]][row["level"]] = row["count"]

            status["timeline_view"]["by_date"] = dict(timeline_data)

        return status

    def get_audit_status(self) -> Dict[str, Any]:
        """Get audit trail status and basic integrity check."""
        status = {"audit_trail": {}, "hash_chain": {}, "signatures": {}, "integrity": {}}

        if not Path(self.audit_db_path).exists():
            status["error"] = "Audit database not found"
            return status

        with self.get_connection(str(self.audit_db_path)) as conn:
            cursor = conn.cursor()

            # Basic stats
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_entries,
                    MIN(event_timestamp) as oldest_entry,
                    MAX(event_timestamp) as newest_entry,
                    MIN(sequence_number) as min_seq,
                    MAX(sequence_number) as max_seq
                FROM audit_log
            """
            )

            row = cursor.fetchone()
            if row and row["total_entries"] > 0:
                status["audit_trail"] = {
                    "total_entries": row["total_entries"],
                    "oldest_entry": row["oldest_entry"],
                    "newest_entry": row["newest_entry"],
                    "sequence_range": (row["min_seq"], row["max_seq"]),
                    "expected_entries": row["max_seq"] - row["min_seq"] + 1,
                }

                # Check for sequence gaps
                cursor.execute(
                    """
                    WITH seq_range AS (
                        SELECT MIN(sequence_number) as min_seq, MAX(sequence_number) as max_seq
                        FROM audit_log
                    ),
                    expected AS (
                        SELECT min_seq + level as expected_seq
                        FROM seq_range, (
                            WITH RECURSIVE levels(level) AS (
                                SELECT 0
                                UNION ALL
                                SELECT level + 1 FROM levels
                                WHERE level < (SELECT max_seq - min_seq FROM seq_range)
                            )
                            SELECT level FROM levels
                        )
                    )
                    SELECT COUNT(*) as missing_count
                    FROM expected
                    LEFT JOIN audit_log ON expected.expected_seq = audit_log.sequence_number
                    WHERE audit_log.sequence_number IS NULL
                """
                )

                missing_count = cursor.fetchone()["missing_count"]
                status["integrity"]["sequence_gaps"] = missing_count
                status["integrity"]["sequence_complete"] = missing_count == 0

            # Hash chain spot check
            cursor.execute(
                """
                SELECT sequence_number, previous_hash, entry_hash
                FROM audit_log
                ORDER BY sequence_number DESC
                LIMIT 10
            """
            )

            recent_entries = list(cursor)
            if len(recent_entries) >= 2:
                # Quick check: verify last entry links to previous
                last = recent_entries[0]
                prev = recent_entries[1]

                status["hash_chain"]["last_entry_seq"] = last["sequence_number"]
                status["hash_chain"]["last_entry_hash"] = last["entry_hash"][:16] + "..."
                status["hash_chain"]["links_to_previous"] = last["previous_hash"] == prev["entry_hash"]

            # Signature stats
            cursor.execute(
                """
                SELECT
                    COUNT(CASE WHEN signature IS NOT NULL THEN 1 END) as signed_entries,
                    COUNT(CASE WHEN signature IS NULL THEN 1 END) as unsigned_entries,
                    COUNT(DISTINCT signing_key_id) as unique_keys_used
                FROM audit_log
            """
            )

            row = cursor.fetchone()
            status["signatures"] = {
                "signed_entries": row["signed_entries"],
                "unsigned_entries": row["unsigned_entries"],
                "unique_keys_used": row["unique_keys_used"],
            }

            # Get active signing keys
            cursor.execute(
                """
                SELECT key_id, created_at, revoked_at
                FROM audit_signing_keys
                ORDER BY created_at DESC
            """
            )

            keys = list(cursor)
            status["signatures"]["total_keys"] = len(keys)
            status["signatures"]["active_keys"] = sum(1 for k in keys if not k["revoked_at"])
            status["signatures"]["revoked_keys"] = sum(1 for k in keys if k["revoked_at"])

        return status

    def verify_audit_integrity(self, sample_size: Optional[int] = None):
        """Run comprehensive audit verification."""
        # Get the key path from the parent directory of db_path
        key_path = Path(self.db_path).parent / "audit_keys"

        # Create a simple time service
        from datetime import datetime, timezone

        class SimpleTimeService:
            def now(self):
                return datetime.now(timezone.utc)

        verifier = AuditVerifier(
            db_path=str(self.audit_db_path), key_path=str(key_path), time_service=SimpleTimeService()
        )

        if sample_size:
            # Verify a sample - verify the first N entries
            return verifier.verify_range(1, sample_size)
        else:
            # Full verification
            return verifier.verify_complete_chain()

    def get_consolidated_state_analysis(self) -> Dict[str, Any]:
        """Analyze the current consolidated state of the database."""
        analysis = {"summary_types": {}, "consolidation_coverage": {}, "edge_connectivity": {}, "data_retention": {}}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Analyze summary types and their consolidation levels
            cursor.execute(
                """
                SELECT
                    node_type,
                    json_extract(attributes_json, '$.consolidation_level') as level,
                    COUNT(*) as count,
                    MIN(json_extract(attributes_json, '$.period_start')) as earliest,
                    MAX(json_extract(attributes_json, '$.period_end')) as latest
                FROM graph_nodes
                WHERE node_type IN ('tsdb_summary', 'audit_summary', 'trace_summary',
                                   'task_summary', 'conversation_summary')
                GROUP BY node_type, level
                ORDER BY node_type, level
            """
            )

            for row in cursor:
                node_type = row["node_type"]
                if node_type not in analysis["summary_types"]:
                    analysis["summary_types"][node_type] = {}
                level = row["level"] or "basic"
                analysis["summary_types"][node_type][level] = {
                    "count": row["count"],
                    "earliest": row["earliest"],
                    "latest": row["latest"],
                }

            # Check edge connectivity
            cursor.execute(
                """
                SELECT
                    relationship,
                    COUNT(*) as count
                FROM graph_edges
                WHERE relationship IN ('TEMPORAL_PREV', 'TEMPORAL_NEXT',
                                     'SAME_DAY_SUMMARY', 'SUMMARIZES')
                GROUP BY relationship
            """
            )

            analysis["edge_connectivity"]["by_type"] = {row["relationship"]: row["count"] for row in cursor}

            # Analyze data retention status
            now_str = datetime.now(timezone.utc).isoformat()

            # Raw data older than 24 hours
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                  AND created_at < datetime(?, '-24 hours')
            """,
                (now_str,),
            )

            analysis["data_retention"]["raw_data_old"] = cursor.fetchone()["count"]

            # Basic summaries older than 7 days
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE node_type LIKE '%_summary'
                  AND (json_extract(attributes_json, '$.consolidation_level') = 'basic'
                       OR json_extract(attributes_json, '$.consolidation_level') IS NULL)
                  AND json_extract(attributes_json, '$.period_start') < datetime(?, '-7 days')
            """,
                (now_str,),
            )

            analysis["data_retention"]["basic_summaries_old"] = cursor.fetchone()["count"]

            # Daily summaries older than 30 days
            cursor.execute(
                """
                SELECT COUNT(*) as count
                FROM graph_nodes
                WHERE node_type LIKE '%_summary'
                  AND json_extract(attributes_json, '$.consolidation_level') = 'extensive'
                  AND json_extract(attributes_json, '$.period_start') < datetime(?, '-30 days')
            """,
                (now_str,),
            )

            analysis["data_retention"]["daily_summaries_old"] = cursor.fetchone()["count"]

        return analysis

    def get_available_test_periods(self) -> Dict[str, Any]:
        """Get available data periods for testing consolidation."""
        periods = {"raw_data": {}, "unconsolidated": {}, "recommendations": []}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Find periods with raw data
            cursor.execute(
                """
                SELECT
                    DATE(created_at) as date,
                    COUNT(*) as node_count,
                    MIN(created_at) as earliest,
                    MAX(created_at) as latest
                FROM graph_nodes
                WHERE node_type IN ('tsdb_data', 'audit_entry')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            """
            )

            raw_periods = list(cursor)
            periods["raw_data"]["by_date"] = []

            for row in raw_periods:
                periods["raw_data"]["by_date"].append(
                    {
                        "date": row["date"],
                        "node_count": row["node_count"],
                        "time_range": (row["earliest"], row["latest"]),
                    }
                )

            # Find unconsolidated periods
            cursor.execute(
                """
                WITH consolidated_periods AS (
                    SELECT
                        json_extract(attributes_json, '$.period_start') as period_start,
                        json_extract(attributes_json, '$.period_end') as period_end,
                        json_extract(attributes_json, '$.consolidation_level') as level
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                )
                SELECT
                    strftime('%Y-%m-%d %H:00:00', created_at) as hour_slot,
                    COUNT(*) as node_count
                FROM graph_nodes
                WHERE node_type = 'tsdb_data'
                  AND NOT EXISTS (
                      SELECT 1 FROM consolidated_periods
                      WHERE datetime(graph_nodes.created_at) >= datetime(period_start)
                        AND datetime(graph_nodes.created_at) < datetime(period_end)
                  )
                GROUP BY hour_slot
                ORDER BY hour_slot DESC
                LIMIT 100
            """
            )

            unconsolidated = list(cursor)
            periods["unconsolidated"]["hours"] = []

            for row in unconsolidated:
                periods["unconsolidated"]["hours"].append({"hour": row["hour_slot"], "node_count": row["node_count"]})

            # Generate recommendations
            if raw_periods:
                oldest_date = raw_periods[-1]["date"]
                newest_date = raw_periods[0]["date"]

                periods["recommendations"].append(
                    {
                        "type": "basic_consolidation",
                        "reason": f"Found {len(unconsolidated)} hours with unconsolidated data",
                        "suggested_period": "Any 6-hour period with raw data",
                    }
                )

                # Check for weekly consolidation opportunity
                oldest_dt = datetime.fromisoformat(oldest_date)
                newest_dt = datetime.fromisoformat(newest_date)

                if (newest_dt - oldest_dt).days >= 7:
                    periods["recommendations"].append(
                        {
                            "type": "extensive_consolidation",
                            "reason": "At least 7 days of data available",
                            "suggested_period": "Previous Monday-Sunday period",
                        }
                    )

                if (newest_dt - oldest_dt).days >= 30:
                    periods["recommendations"].append(
                        {
                            "type": "profound_consolidation",
                            "reason": "At least 30 days of data available",
                            "suggested_period": "Previous calendar month",
                        }
                    )

        return periods

    def get_tsdb_node_age_analysis(self) -> Dict[str, Any]:
        """Analyze TSDB data nodes by age to identify consolidation issues."""
        result = {
            "tsdb_data_nodes": {
                "within_30h": 0,  # Expected - before first consolidation
                "between_30_36h": 0,  # May be OK - waiting for next run
                "over_36h": 0,  # Should have been consolidated
                "total": 0,
            },
            "basic_summaries": {
                "within_7d": 0,  # Expected retention
                "over_7d": 0,  # Should have been consolidated to daily
                "over_15d": 0,  # Definitely should be gone
                "total": 0,
            },
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
                    "over_7d": row["over_7d"] - row["over_15d"],  # 7-15 days
                    "over_15d": row["over_15d"],
                }

            # Generate recommendations
            if result["tsdb_data_nodes"]["over_36h"] > 0:
                result["recommendations"].append(
                    {
                        "severity": "HIGH",
                        "issue": f"{result['tsdb_data_nodes']['over_36h']:,} TSDB data nodes older than 36 hours",
                        "action": "Check if consolidation service is running properly",
                    }
                )

            if result["tsdb_data_nodes"]["between_30_36h"] > 100:
                result["recommendations"].append(
                    {
                        "severity": "MEDIUM",
                        "issue": f"{result['tsdb_data_nodes']['between_30_36h']:,} nodes waiting for consolidation",
                        "action": "Normal if consolidation is about to run",
                    }
                )

            if result["basic_summaries"]["over_7d"] > 0:
                result["recommendations"].append(
                    {
                        "severity": "MEDIUM",
                        "issue": f"{result['basic_summaries']['over_7d']:,} basic summaries older than 7 days",
                        "action": "Should be consolidated to daily summaries",
                    }
                )

            if result["basic_summaries"]["over_15d"] > 0:
                result["recommendations"].append(
                    {
                        "severity": "HIGH",
                        "issue": f"{result['basic_summaries']['over_15d']:,} basic summaries older than 15 days",
                        "action": "Extensive consolidation may not be running",
                    }
                )

        return result

    def get_nodes_without_edges(self, limit: int = 100) -> Dict[str, Any]:
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

            # Analysis - check age of orphaned nodes
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

    def print_nodes_without_edges(self):
        """Print report on orphaned nodes."""
        self.print_section("NODES WITHOUT EDGES (ORPHANED)")

        orphaned = self.get_nodes_without_edges()

        print(f"\nTotal Orphaned Nodes: {orphaned['total_orphaned']:,}")

        if orphaned["by_type"]:
            self.print_subsection("Orphaned Nodes by Type")
            for node_type, count in orphaned["by_type"].items():
                print(f"  {node_type}: {count:,}")

        if orphaned["analysis"]["age_distribution"]:
            self.print_subsection("Age Distribution")
            age = orphaned["analysis"]["age_distribution"]
            print(f"  Created in last hour: {age['last_hour']:,}")
            print(f"  Created in last 6 hours: {age['last_6_hours']:,}")
            print(f"  Created in last 24 hours: {age['last_24_hours']:,}")
            print(f"  Created in last 7 days: {age['last_7_days']:,}")

        if orphaned["sample_nodes"]:
            self.print_subsection("Sample Orphaned Nodes (newest first)")
            print("\nNode ID                              | Type       | Created")
            print("-" * 70)
            for node in orphaned["sample_nodes"][:20]:
                created = node["created_at"][:19] if node["created_at"] else "Unknown"
                print(f"{node['node_id'][:35]:35} | {node['node_type']:10} | {created}")

    def print_status_report(self):
        """Print comprehensive status report."""
        self.print_section("CIRIS DATABASE STATUS REPORT")

        # Overall status
        status = self.get_overall_status()

        self.print_subsection("Database Files")

        if status["main_db"].get("exists"):
            print(f"Main DB: {self.db_path}")
            print(f"  Size: {self.format_size(status['main_db']['size'])}")
            print(f"  Modified: {status['main_db']['modified'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        else:
            print(f"Main DB: NOT FOUND at {self.db_path}")

        if status["audit_db"].get("exists"):
            print(f"\nAudit DB: {self.audit_db_path}")
            print(f"  Size: {self.format_size(status['audit_db']['size'])}")
            print(f"  Entries: {status['audit_db']['entries']:,}")
            if "sequence_range" in status["audit_db"]:
                seq_min, seq_max = status["audit_db"]["sequence_range"]
                print(f"  Sequence Range: {seq_min:,} - {seq_max:,}")
        else:
            print(f"\nAudit DB: NOT FOUND at {self.audit_db_path}")

        # Graph nodes
        if status["graph_nodes"].get("total"):
            self.print_subsection("Graph Nodes")
            print(f"Total Nodes: {status['graph_nodes']['total']:,}")

            if status["graph_nodes"].get("oldest"):
                # Handle both timezone-aware and naive datetimes
                oldest_str = status["graph_nodes"]["oldest"]
                newest_str = status["graph_nodes"]["newest"]

                # Parse timestamps
                if "Z" in oldest_str:
                    oldest = datetime.fromisoformat(oldest_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                elif "+" in oldest_str or "T" in oldest_str:
                    oldest = datetime.fromisoformat(oldest_str)
                else:
                    # Assume UTC for naive timestamps
                    oldest = datetime.fromisoformat(oldest_str).replace(tzinfo=timezone.utc)

                if "Z" in newest_str:
                    newest = datetime.fromisoformat(newest_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                elif "+" in newest_str or "T" in newest_str:
                    newest = datetime.fromisoformat(newest_str)
                else:
                    newest = datetime.fromisoformat(newest_str).replace(tzinfo=timezone.utc)

                age = datetime.now(timezone.utc) - oldest

                print(f"Date Range: {oldest.strftime('%Y-%m-%d')} to {newest.strftime('%Y-%m-%d')}")
                print(f"Data Age: {self.format_timedelta(age)}")

            print("\nNodes by Type:")
            for node_type, count in sorted(status["graph_nodes"]["by_type"].items(), key=lambda x: x[1], reverse=True)[
                :10
            ]:
                print(f"  {node_type}: {count:,}")

        # Service correlations
        if status["correlations"].get("total"):
            self.print_subsection("Service Correlations")
            print(f"Total Correlations: {status['correlations']['total']:,}")
            if status["correlations"].get("by_type"):
                print("\nBy Type:")
                for corr_type, count in sorted(
                    status["correlations"]["by_type"].items(), key=lambda x: x[1], reverse=True
                ):
                    print(f"  {corr_type}: {count:,}")

        # Tasks and Thoughts
        if status["tasks"].get("total") or status["thoughts"].get("total"):
            self.print_subsection("Tasks and Thoughts")

            if status["tasks"].get("total"):
                print(f"Total Tasks: {status['tasks']['total']:,}")
                for status_name, count in status["tasks"]["by_status"].items():
                    print(f"  {status_name}: {count:,}")

            if status["thoughts"].get("total"):
                print(f"\nTotal Thoughts: {status['thoughts']['total']:,}")
                for status_name, count in status["thoughts"]["by_status"].items():
                    print(f"  {status_name}: {count:,}")

    def print_tsdb_report(self):
        """Print TSDB consolidation report."""
        self.print_section("TSDB CONSOLIDATION STATUS")

        status = self.get_tsdb_status()

        # Consolidation summaries
        self.print_subsection("Consolidation Summaries")

        total_summaries = sum(status["consolidation_summaries"].values())
        print(f"Total Summaries: {total_summaries}")

        for level in ["basic", "extensive", "profound"]:
            count = status["consolidation_summaries"].get(level, 0)
            print(f"  {level.capitalize()}: {count}")

        # Last consolidations
        self.print_subsection("Last Consolidation Runs")

        for level in ["basic", "extensive", "profound"]:
            if level in status["last_consolidations"]:
                info = status["last_consolidations"][level]
                last_run_str = info["last_run"]

                # Parse timestamp
                if "Z" in last_run_str:
                    last_run = datetime.fromisoformat(last_run_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                elif "+" in last_run_str or "T" in last_run_str:
                    last_run = datetime.fromisoformat(last_run_str)
                else:
                    last_run = datetime.fromisoformat(last_run_str).replace(tzinfo=timezone.utc)

                age = datetime.now(timezone.utc) - last_run

                print(f"\n{level.capitalize()} Consolidation:")
                print(f"  Last Run: {last_run.strftime('%Y-%m-%d %H:%M:%S UTC')} ({self.format_timedelta(age)} ago)")
                print(f"  Period: {info['period_label']}")
                print(f"  Range: {info['period_start']} to {info['period_end']}")
            else:
                print(f"\n{level.capitalize()} Consolidation: NEVER RUN")

        # Data coverage
        if status["data_coverage"].get("consolidation_gaps"):
            gaps = status["data_coverage"]["consolidation_gaps"]
            self.print_subsection("Consolidation Coverage (Last 30 Days)")
            print(f"Expected Basic Consolidations: {gaps['expected_basic_30d']}")
            print(f"Actual Basic Consolidations: {gaps['actual_basic_30d']}")
            print(f"Coverage: {gaps['coverage_percent']:.1f}%")

        # Timeline view
        if status["timeline_view"].get("by_date"):
            self.print_subsection("Consolidation Timeline View")
            print("\nDate       | Basic | Daily | Monthly")
            print("-" * 40)

            dates = sorted(status["timeline_view"]["by_date"].keys(), reverse=True)
            for date in dates[:14]:  # Show last 2 weeks
                levels = status["timeline_view"]["by_date"][date]
                basic = levels.get("basic", 0)
                extensive = levels.get("extensive", 0)
                profound = levels.get("profound", 0)
                print(f"{date} | {basic:5} | {extensive:5} | {profound:7}")

        # Recent metrics
        if status["metrics"].get("top_metrics_7d"):
            self.print_subsection("Top Metrics (Last 7 Days)")
            for i, (metric, count) in enumerate(list(status["metrics"]["top_metrics_7d"].items())[:10]):
                print(f"  {i+1}. {metric}: {count:,}")

        # Daily data
        if status["data_coverage"].get("daily_metrics"):
            self.print_subsection("Daily Metrics Coverage")
            print("Date       | Nodes | Total Value")
            print("-" * 35)
            for day in status["data_coverage"]["daily_metrics"][:7]:
                value_str = f"{day['total_value']:.2f}" if day["total_value"] else "N/A"
                print(f"{day['date']} | {day['node_count']:5} | {value_str}")

    def print_audit_report(self):
        """Print audit integrity report."""
        self.print_section("AUDIT TRAIL INTEGRITY")

        status = self.get_audit_status()

        if "error" in status:
            print(f"ERROR: {status['error']}")
            return

        # Basic stats
        if status["audit_trail"]:
            trail = status["audit_trail"]
            self.print_subsection("Audit Trail Statistics")
            print(f"Total Entries: {trail['total_entries']:,}")

            # Parse timestamps
            oldest_str = trail["oldest_entry"]
            newest_str = trail["newest_entry"]

            if "Z" in oldest_str:
                oldest = datetime.fromisoformat(oldest_str.replace("Z", UTC_TIMEZONE_SUFFIX))
            elif "+" in oldest_str or "T" in oldest_str:
                oldest = datetime.fromisoformat(oldest_str)
            else:
                oldest = datetime.fromisoformat(oldest_str).replace(tzinfo=timezone.utc)

            if "Z" in newest_str:
                newest = datetime.fromisoformat(newest_str.replace("Z", UTC_TIMEZONE_SUFFIX))
            elif "+" in newest_str or "T" in newest_str:
                newest = datetime.fromisoformat(newest_str)
            else:
                newest = datetime.fromisoformat(newest_str).replace(tzinfo=timezone.utc)

            print(f"Date Range: {oldest.strftime('%Y-%m-%d %H:%M')} to {newest.strftime('%Y-%m-%d %H:%M')}")
            print(f"Sequence Range: {trail['sequence_range'][0]:,} to {trail['sequence_range'][1]:,}")
            print(f"Expected Entries: {trail['expected_entries']:,}")

        # Integrity check
        if status["integrity"]:
            self.print_subsection("Integrity Check")
            print(f"Sequence Complete: {'✓ YES' if status['integrity']['sequence_complete'] else '✗ NO'}")
            if not status["integrity"]["sequence_complete"]:
                print(f"  Missing Sequences: {status['integrity']['sequence_gaps']}")

        # Hash chain
        if status["hash_chain"]:
            chain = status["hash_chain"]
            self.print_subsection("Hash Chain")
            print(f"Last Entry: Seq #{chain['last_entry_seq']}")
            print(f"Hash: {chain['last_entry_hash']}")
            print(f"Links Correctly: {'✓ YES' if chain['links_to_previous'] else '✗ NO'}")

        # Signatures
        if status["signatures"]:
            sigs = status["signatures"]
            self.print_subsection("Digital Signatures")
            print(f"Signed Entries: {sigs['signed_entries']:,}")
            print(f"Unsigned Entries: {sigs['unsigned_entries']:,}")
            print(
                f"Signature Coverage: {sigs['signed_entries'] / (sigs['signed_entries'] + sigs['unsigned_entries']) * 100:.1f}%"
            )
            print("\nSigning Keys:")
            print(f"  Total: {sigs['total_keys']}")
            print(f"  Active: {sigs['active_keys']}")
            print(f"  Revoked: {sigs['revoked_keys']}")
            print(f"  Unique Keys Used: {sigs['unique_keys_used']}")

    def print_verification_report(self, sample_size: Optional[int] = None):
        """Run and print comprehensive verification."""
        self.print_section("COMPREHENSIVE AUDIT VERIFICATION")

        if sample_size:
            print(f"Running verification on sample of {sample_size} entries...")
        else:
            print("Running FULL chain verification (this may take a while)...")

        print()

        try:
            report = self.verify_audit_integrity(sample_size)

            # Print results based on report type
            if hasattr(report, "valid"):  # Both CompleteVerificationResult and RangeVerificationResult have 'valid'
                print(f"Verification {'PASSED ✓' if report.valid else 'FAILED ✗'}")
            else:
                print(f"Verification {'PASSED ✓' if report.is_valid else 'FAILED ✗'}")

            print(f"Entries Verified: {report.entries_verified:,}")

            if hasattr(report, "verification_time"):
                print(f"Time Taken: {report.verification_time:.2f} seconds")

            if hasattr(report, "errors") and report.errors:
                self.print_subsection("Errors Found")
                for error in report.errors[:10]:  # Show first 10 errors
                    print(f"  - {error}")
                if len(report.errors) > 10:
                    print(f"  ... and {len(report.errors) - 10} more errors")

            if hasattr(report, "warnings") and report.warnings:
                self.print_subsection("Warnings")
                for warning in report.warnings[:5]:
                    print(f"  - {warning}")
                if len(report.warnings) > 5:
                    print(f"  ... and {len(report.warnings) - 5} more warnings")

            if hasattr(report, "metadata") and report.metadata:
                self.print_subsection("Verification Details")
                for key, value in report.metadata.items():
                    print(f"  {key}: {value}")

        except Exception as e:
            print(f"ERROR: Verification failed - {e}")

    def print_test_periods(self):
        """Print available test periods."""
        self.print_section("AVAILABLE TEST PERIODS")

        periods = self.get_available_test_periods()

        # Raw data summary
        if periods["raw_data"].get("by_date"):
            self.print_subsection("Raw Data Available")

            dates = periods["raw_data"]["by_date"]
            oldest = dates[-1]["date"]
            newest = dates[0]["date"]
            total_nodes = sum(d["node_count"] for d in dates)

            print(f"Date Range: {oldest} to {newest}")
            print(f"Total Days: {len(dates)}")
            print(f"Total Nodes: {total_nodes:,}")

            print("\nRecent Days:")
            print("Date       | Nodes")
            print("-" * 20)
            for day in dates[:7]:
                print(f"{day['date']} | {day['node_count']:,}")

        # Unconsolidated periods
        if periods["unconsolidated"].get("hours"):
            hours = periods["unconsolidated"]["hours"]
            self.print_subsection("Unconsolidated Hours")

            print(f"Total Hours: {len(hours)}")
            print("\nRecent Hours:")
            print("Hour                | Nodes")
            print("-" * 30)
            for hour in hours[:10]:
                print(f"{hour['hour']} | {hour['node_count']:,}")

        # Recommendations
        if periods["recommendations"]:
            self.print_subsection("Testing Recommendations")

            for i, rec in enumerate(periods["recommendations"], 1):
                print(f"\n{i}. {rec['type'].replace('_', ' ').title()}")
                print(f"   Reason: {rec['reason']}")
                print(f"   Suggested: {rec['suggested_period']}")

    def print_consolidated_state_analysis(self):
        """Print analysis of the consolidated state."""
        self.print_section("CONSOLIDATED STATE ANALYSIS")

        analysis = self.get_consolidated_state_analysis()

        # Summary types and levels
        if analysis["summary_types"]:
            self.print_subsection("Summary Node Distribution")
            print("\nType                | Basic | Daily | Monthly | Total")
            print("-" * 55)

            for node_type in sorted(analysis["summary_types"].keys()):
                levels = analysis["summary_types"][node_type]
                basic = levels.get("basic", {}).get("count", 0)
                extensive = levels.get("extensive", {}).get("count", 0)
                profound = levels.get("profound", {}).get("count", 0)
                total = basic + extensive + profound

                print(f"{node_type:18} | {basic:5} | {extensive:5} | {profound:7} | {total:5}")

        # Edge connectivity
        if analysis["edge_connectivity"].get("by_type"):
            self.print_subsection("Graph Edge Connectivity")
            edges = analysis["edge_connectivity"]["by_type"]
            print(f"Temporal Previous: {edges.get('TEMPORAL_PREV', 0):,}")
            print(f"Temporal Next: {edges.get('TEMPORAL_NEXT', 0):,}")
            print(f"Same Day Links: {edges.get('SAME_DAY_SUMMARY', 0):,}")
            print(f"Summarizes: {edges.get('SUMMARIZES', 0):,}")

        # Data retention status
        if analysis["data_retention"]:
            self.print_subsection("Data Retention Status")
            retention = analysis["data_retention"]

            if retention["raw_data_old"] > 0:
                print(f"⚠️  Raw data older than 24h: {retention['raw_data_old']:,} nodes (should be cleaned)")
            else:
                print("✓ No raw data older than 24h")

            if retention["basic_summaries_old"] > 0:
                print(
                    f"⚠️  Basic summaries older than 7d: {retention['basic_summaries_old']:,} nodes (should be cleaned)"
                )
            else:
                print("✓ No basic summaries older than 7 days")

            if retention["daily_summaries_old"] > 0:
                print(
                    f"⚠️  Daily summaries older than 30d: {retention['daily_summaries_old']:,} nodes (should be cleaned)"
                )
            else:
                print("✓ No daily summaries older than 30 days")

    def get_critical_issues(self) -> List[Dict[str, str]]:
        """Check for critical issues that need immediate attention."""
        issues = []

        # Check for orphaned nodes in consolidated periods
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Find nodes without edges in consolidated periods
            cursor.execute(
                """
                WITH consolidated_periods AS (
                    SELECT DISTINCT
                        json_extract(attributes_json, '$.period_start') as period_start,
                        json_extract(attributes_json, '$.period_end') as period_end,
                        node_id as summary_id
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                )
                SELECT COUNT(*) as orphaned_count
                FROM graph_nodes n
                INNER JOIN consolidated_periods p
                    ON datetime(n.created_at) >= datetime(p.period_start)
                    AND datetime(n.created_at) < datetime(p.period_end)
                WHERE n.scope = 'local'
                    AND n.node_type != 'tsdb_data'
                    AND NOT EXISTS (
                        SELECT 1 FROM graph_edges e
                        WHERE e.source_node_id = p.summary_id
                            AND e.target_node_id = n.node_id
                            AND e.relationship = 'SUMMARIZES'
                    )
            """
            )

            orphaned_count = cursor.fetchone()["orphaned_count"]
            if orphaned_count > 0:
                issues.append(
                    {
                        "severity": "CRITICAL",
                        "issue": f"{orphaned_count} orphaned nodes in consolidated periods",
                        "detail": "Nodes exist in same scope as summaries but have no SUMMARIZES edges",
                        "action": "Run edge recalculation for affected periods",
                    }
                )

        # Check TSDB node age
        age_analysis = self.get_tsdb_node_age_analysis()
        if age_analysis["tsdb_data_nodes"]["over_36h"] > 0:
            issues.append(
                {
                    "severity": "HIGH",
                    "issue": f"{age_analysis['tsdb_data_nodes']['over_36h']} TSDB nodes older than 36 hours",
                    "detail": "These nodes should have been consolidated",
                    "action": "Check consolidation service health",
                }
            )

        # Check basic summaries age
        if age_analysis["basic_summaries"]["over_15d"] > 0:
            issues.append(
                {
                    "severity": "HIGH",
                    "issue": f"{age_analysis['basic_summaries']['over_15d']} basic summaries older than 15 days",
                    "detail": "These should have been consolidated to daily summaries",
                    "action": "Check extensive consolidation service",
                }
            )

        return issues

    def print_full_report(self):
        """Print complete status report."""
        print("\n" + "=" * 80)
        print("CIRIS COMPREHENSIVE DATABASE REPORT".center(80))
        print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}".center(80))
        print("=" * 80)

        # Check for critical issues first
        issues = self.get_critical_issues()
        if issues:
            print("\n" + "🚨 CRITICAL ISSUES DETECTED 🚨".center(80))
            print("-" * 80)
            for issue in issues:
                print(f"\n[{issue['severity']}] {issue['issue']}")
                print(f"  Details: {issue['detail']}")
                print(f"  Action: {issue['action']}")
            print("\n" + "-" * 80)
            print("See 'ciris_db_tools comprehensive' for detailed analysis")
            print("-" * 80)

        self.print_status_report()
        self.print_tsdb_report()
        self.print_consolidated_state_analysis()
        self.print_audit_report()
        self.print_test_periods()

        print("\n" + "=" * 80)
        print("END OF REPORT".center(80))
        print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="CIRIS Database Status and Integrity Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python db_status_tool.py              # Full status report
  python db_status_tool.py status       # Overall database status
  python db_status_tool.py tsdb         # TSDB consolidation details
  python db_status_tool.py audit        # Audit trail status
  python db_status_tool.py verify       # Full audit verification
  python db_status_tool.py verify 1000  # Verify sample of 1000 entries
  python db_status_tool.py periods      # Available test periods
        """,
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="all",
        choices=["all", "status", "tsdb", "audit", "verify", "periods", "consolidation", "orphaned"],
        help="Command to run (default: all)",
    )

    parser.add_argument(
        "sample_size", nargs="?", type=int, help="Sample size for verify command (omit for full verification)"
    )

    parser.add_argument("--db-path", help="Path to main database (default: auto-detect)")

    args = parser.parse_args()

    # Create tool instance
    tool = DBStatusTool(args.db_path)

    # Run requested command
    try:
        if args.command == "all":
            tool.print_full_report()
        elif args.command == "status":
            tool.print_status_report()
        elif args.command == "tsdb":
            tool.print_tsdb_report()
        elif args.command == "audit":
            tool.print_audit_report()
        elif args.command == "verify":
            tool.print_verification_report(args.sample_size)
        elif args.command == "periods":
            tool.print_test_periods()
        elif args.command == "consolidation":
            tool.print_tsdb_report()
            tool.print_consolidated_state_analysis()
        elif args.command == "orphaned":
            tool.print_nodes_without_edges()

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
