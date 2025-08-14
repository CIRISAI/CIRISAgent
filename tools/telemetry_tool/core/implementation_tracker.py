#!/usr/bin/env python3
"""
MDD Implementation Tracker
Tracks which telemetry endpoints are implemented vs pending
Distinguishes mission-critical from supporting metrics
"""

import ast
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MetricPriority(str, Enum):
    """Metric priority for mission-driven development"""

    MISSION_CRITICAL = "MISSION_CRITICAL"  # Directly serves M-1
    MISSION_SUPPORTING = "MISSION_SUPPORTING"  # Required for mission
    OPERATIONAL = "OPERATIONAL"  # Pure ops metrics
    NICE_TO_HAVE = "NICE_TO_HAVE"  # Low priority


class EndpointStatus(str, Enum):
    """Implementation status of an endpoint"""

    IMPLEMENTED = "IMPLEMENTED"
    PARTIAL = "PARTIAL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    DEPRECATED = "DEPRECATED"


@dataclass
class TelemetryEndpoint:
    """Represents a telemetry endpoint to implement"""

    module_name: str
    metric_name: str
    metric_type: str  # counter, gauge, histogram
    endpoint_path: str
    http_method: str
    priority: MetricPriority
    status: EndpointStatus
    implementation_path: Optional[str] = None
    notes: Optional[str] = None


class ImplementationTracker:
    """Track telemetry endpoint implementation status"""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the tracker with database"""
        if db_path is None:
            db_path = "/home/emoore/CIRISAgent/tools/telemetry_tool/data/implementation.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path))
        self._init_database()

        # Paths to scan
        self.api_path = Path("/home/emoore/CIRISAgent/ciris_engine/api")
        self.docs_path = Path("/home/emoore/CIRISAgent/ciris_engine/docs/telemetry")

    def _init_database(self):
        """Initialize the implementation tracking database"""
        cursor = self.conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS endpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_type TEXT NOT NULL,
                endpoint_path TEXT NOT NULL,
                http_method TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL,
                implementation_path TEXT,
                notes TEXT,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(module_name, metric_name, endpoint_path)
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS implementation_stats (
                module_name TEXT PRIMARY KEY,
                total_metrics INTEGER,
                implemented INTEGER,
                partial INTEGER,
                not_implemented INTEGER,
                mission_critical_done INTEGER,
                mission_critical_total INTEGER,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        self.conn.commit()

    def classify_metric_priority(self, module_name: str, metric_name: str, metric_type: str) -> MetricPriority:
        """
        Classify metric priority based on mission alignment

        Mission-Critical: Directly impacts user flourishing
        Supporting: Required for mission-critical to function
        Operational: System health and debugging
        """
        metric_lower = metric_name.lower()
        module_lower = module_name.lower()

        # Mission-Critical: Direct user impact
        mission_critical_patterns = [
            "user_benefit",
            "harm_prevented",
            "guidance_",
            "wisdom_",
            "transparency_",
            "audit_",
            "consent_",
            "privacy_",
            "fairness_",
            "equity_",
            "decision_",
            "intervention_",
            "safety_",
            "trust_",
            "ethical_",
            "covenant_",
        ]

        # Mission-Supporting: Required for mission
        supporting_patterns = [
            "error_",
            "timeout_",
            "circuit_breaker",
            "fallback_",
            "validation_",
            "auth_",
            "rate_limit",
            "resource_",
            "queue_depth",
            "processing_time",
            "latency_critical",
        ]

        # Check patterns
        for pattern in mission_critical_patterns:
            if pattern in metric_lower:
                return MetricPriority.MISSION_CRITICAL

        for pattern in supporting_patterns:
            if pattern in metric_lower:
                return MetricPriority.MISSION_SUPPORTING

        # Special cases by module
        if "wise_authority" in module_lower or "adaptive_filter" in module_lower:
            return MetricPriority.MISSION_CRITICAL

        if "audit" in module_lower or "visibility" in module_lower:
            return MetricPriority.MISSION_CRITICAL

        # Default based on metric type
        if metric_type == "histogram" and "latency" in metric_lower:
            return MetricPriority.MISSION_SUPPORTING

        return MetricPriority.OPERATIONAL

    def scan_implemented_endpoints(self) -> Dict[str, EndpointStatus]:
        """Scan codebase for implemented telemetry endpoints"""
        implemented = {}

        # Check the actual API routes directory
        routes_path = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes")

        if routes_path.exists():
            for py_file in routes_path.glob("*.py"):
                content = py_file.read_text()

                # Find FastAPI route definitions
                # Look for @router.get, @router.post, etc.
                route_pattern = r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
                matches = re.findall(route_pattern, content)

                for method, path in matches:
                    # Store all routes, especially telemetry ones
                    full_path = f"{method.upper()} {path}"
                    implemented[full_path] = EndpointStatus.IMPLEMENTED

                    # Also map to telemetry-style paths
                    if "telemetry" in py_file.name.lower():
                        # This is the telemetry module
                        module_path = f"/v1/telemetry{path}"
                        implemented[f"{method.upper()} {module_path}"] = EndpointStatus.IMPLEMENTED

        # According to CIRIS_COMPREHENSIVE_GUIDE.md, we have:
        # - 4 Agent endpoints
        # - 10+ System endpoints
        # - 4 Memory endpoints
        # - 4+ Telemetry endpoints
        # - 4 Config endpoints
        # - 4 Auth endpoints
        # - 4 DSAR endpoints
        # - 2 Transparency endpoints
        # - 1 Emergency endpoint
        # Total: 82 endpoints

        # Mark known telemetry endpoints as implemented
        telemetry_endpoints = [
            "GET /metrics",
            "GET /logs",
            "GET /traces",
            "GET /resources",
            "GET /overview",
            "POST /query",
        ]

        for endpoint in telemetry_endpoints:
            method, path = endpoint.split(" ")
            full_path = f"/v1/telemetry{path}"
            implemented[f"{method} {full_path}"] = EndpointStatus.IMPLEMENTED

        return implemented

    def parse_telemetry_docs(self) -> List[TelemetryEndpoint]:
        """Parse telemetry documentation to extract required endpoints"""
        endpoints = []

        if not self.docs_path.exists():
            logger.warning(f"Telemetry docs path not found: {self.docs_path}")
            return endpoints

        for md_file in self.docs_path.rglob("*.md"):
            content = md_file.read_text()
            module_name = md_file.stem.replace("_TELEMETRY", "")

            # Parse metrics table
            in_metrics_table = False
            for line in content.split("\n"):
                if "| Metric Name" in line:
                    in_metrics_table = True
                    continue

                if in_metrics_table and line.startswith("|"):
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if len(parts) >= 4 and parts[0] and "Metric Name" not in parts[0]:
                        metric_name = parts[0]
                        metric_type = parts[1].lower()

                        # Generate endpoint path
                        endpoint_path = f"/v1/telemetry/{module_name.lower()}/{metric_name.lower()}"

                        # Determine HTTP method based on metric type
                        if metric_type == "counter":
                            http_method = "POST"  # Increment counter
                        else:
                            http_method = "GET"  # Read gauge/histogram

                        # Classify priority
                        priority = self.classify_metric_priority(module_name, metric_name, metric_type)

                        endpoint = TelemetryEndpoint(
                            module_name=module_name,
                            metric_name=metric_name,
                            metric_type=metric_type,
                            endpoint_path=endpoint_path,
                            http_method=http_method,
                            priority=priority,
                            status=EndpointStatus.NOT_IMPLEMENTED,
                        )
                        endpoints.append(endpoint)

        return endpoints

    def update_implementation_status(self):
        """Update the implementation status of all endpoints"""
        # Parse required endpoints from docs
        required_endpoints = self.parse_telemetry_docs()

        # Scan for implemented endpoints
        implemented = self.scan_implemented_endpoints()

        # Update status for each endpoint
        cursor = self.conn.cursor()

        for endpoint in required_endpoints:
            # Check if this endpoint is implemented
            key = f"{endpoint.http_method} {endpoint.endpoint_path}"
            if key in implemented:
                endpoint.status = implemented[key]

            # Upsert to database
            cursor.execute(
                """
                INSERT OR REPLACE INTO endpoints
                (module_name, metric_name, metric_type, endpoint_path,
                 http_method, priority, status, implementation_path, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    endpoint.module_name,
                    endpoint.metric_name,
                    endpoint.metric_type,
                    endpoint.endpoint_path,
                    endpoint.http_method,
                    endpoint.priority.value,
                    endpoint.status.value,
                    endpoint.implementation_path,
                    endpoint.notes,
                ),
            )

        self.conn.commit()
        self._update_statistics()

    def _update_statistics(self):
        """Update implementation statistics by module"""
        cursor = self.conn.cursor()

        # Get stats for each module
        cursor.execute(
            """
            SELECT
                module_name,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'IMPLEMENTED' THEN 1 ELSE 0 END) as implemented,
                SUM(CASE WHEN status = 'PARTIAL' THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN status = 'NOT_IMPLEMENTED' THEN 1 ELSE 0 END) as not_implemented,
                SUM(CASE WHEN priority = 'MISSION_CRITICAL' AND status = 'IMPLEMENTED' THEN 1 ELSE 0 END) as mc_done,
                SUM(CASE WHEN priority = 'MISSION_CRITICAL' THEN 1 ELSE 0 END) as mc_total
            FROM endpoints
            GROUP BY module_name
        """
        )

        for row in cursor.fetchall():
            cursor.execute(
                """
                INSERT OR REPLACE INTO implementation_stats
                (module_name, total_metrics, implemented, partial, not_implemented,
                 mission_critical_done, mission_critical_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                row,
            )

        self.conn.commit()

    def get_implementation_report(self) -> Dict[str, Any]:
        """Generate implementation status report"""
        cursor = self.conn.cursor()

        # Overall statistics
        cursor.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'IMPLEMENTED' THEN 1 ELSE 0 END) as implemented,
                SUM(CASE WHEN status = 'PARTIAL' THEN 1 ELSE 0 END) as partial,
                SUM(CASE WHEN status = 'NOT_IMPLEMENTED' THEN 1 ELSE 0 END) as not_implemented
            FROM endpoints
        """
        )
        overall = cursor.fetchone()

        # Priority breakdown
        cursor.execute(
            """
            SELECT
                priority,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'IMPLEMENTED' THEN 1 ELSE 0 END) as implemented
            FROM endpoints
            GROUP BY priority
        """
        )
        priority_stats = cursor.fetchall()

        # Module breakdown
        cursor.execute(
            """
            SELECT * FROM implementation_stats
            ORDER BY mission_critical_done DESC, implemented DESC
        """
        )
        module_stats = cursor.fetchall()

        # Next to implement (mission-critical first)
        cursor.execute(
            """
            SELECT module_name, metric_name, endpoint_path, priority
            FROM endpoints
            WHERE status = 'NOT_IMPLEMENTED'
            ORDER BY
                CASE priority
                    WHEN 'MISSION_CRITICAL' THEN 1
                    WHEN 'MISSION_SUPPORTING' THEN 2
                    WHEN 'OPERATIONAL' THEN 3
                    ELSE 4
                END,
                module_name, metric_name
            LIMIT 20
        """
        )
        next_to_implement = cursor.fetchall()

        return {
            "overall": {
                "total": overall[0],
                "implemented": overall[1],
                "partial": overall[2],
                "not_implemented": overall[3],
                "completion_rate": overall[1] / overall[0] * 100 if overall[0] > 0 else 0,
            },
            "by_priority": [
                {
                    "priority": row[0],
                    "total": row[1],
                    "implemented": row[2],
                    "completion_rate": row[2] / row[1] * 100 if row[1] > 0 else 0,
                }
                for row in priority_stats
            ],
            "by_module": [
                {
                    "module": row[0],
                    "total": row[1],
                    "implemented": row[2],
                    "partial": row[3],
                    "not_implemented": row[4],
                    "mission_critical_done": row[5],
                    "mission_critical_total": row[6],
                }
                for row in module_stats
            ],
            "next_to_implement": [
                {"module": row[0], "metric": row[1], "endpoint": row[2], "priority": row[3]}
                for row in next_to_implement
            ],
        }

    def generate_implementation_guide(self, module_name: Optional[str] = None) -> str:
        """Generate step-by-step implementation guide for pending endpoints"""
        cursor = self.conn.cursor()

        if module_name:
            cursor.execute(
                """
                SELECT * FROM endpoints
                WHERE module_name = ? AND status != 'IMPLEMENTED'
                ORDER BY
                    CASE priority
                        WHEN 'MISSION_CRITICAL' THEN 1
                        WHEN 'MISSION_SUPPORTING' THEN 2
                        WHEN 'OPERATIONAL' THEN 3
                        ELSE 4
                    END
            """,
                (module_name,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM endpoints
                WHERE status != 'IMPLEMENTED' AND priority IN ('MISSION_CRITICAL', 'MISSION_SUPPORTING')
                ORDER BY
                    CASE priority
                        WHEN 'MISSION_CRITICAL' THEN 1
                        WHEN 'MISSION_SUPPORTING' THEN 2
                    END
                LIMIT 10
            """
            )

        endpoints = cursor.fetchall()

        guide = []
        guide.append("# Telemetry Implementation Guide\n")
        guide.append("## Mission-Driven Development Priority\n\n")

        for endpoint in endpoints:
            _, module, metric, metric_type, path, method, priority, status, impl_path, notes, _ = endpoint

            guide.append(f"### {module} - {metric}\n")
            guide.append(f"**Priority**: {priority}\n")
            guide.append(f"**Status**: {status}\n")
            guide.append(f"**Endpoint**: {method} {path}\n")
            guide.append(f"**Type**: {metric_type}\n\n")

            guide.append("```python\n")
            if metric_type == "counter":
                guide.append(f"@router.post('{path}')\n")
                guide.append(f"async def increment_{metric.lower()}(\n")
                guide.append(f"    value: int = 1,\n")
                guide.append(f"    labels: Optional[Dict[str, str]] = None\n")
                guide.append(f") -> Dict[str, Any]:\n")
                guide.append(f"    '''Increment {metric} counter'''\n")
                guide.append(f"    # TODO: Implement counter increment\n")
                guide.append(f"    return {{'status': 'incremented', 'metric': '{metric}', 'value': value}}\n")
            elif metric_type == "gauge":
                guide.append(f"@router.get('{path}')\n")
                guide.append(f"async def get_{metric.lower()}() -> Dict[str, Any]:\n")
                guide.append(f"    '''Get current {metric} gauge value'''\n")
                guide.append(f"    # TODO: Implement gauge reading\n")
                guide.append(f"    return {{'metric': '{metric}', 'value': 0.0}}\n")
            else:  # histogram
                guide.append(f"@router.get('{path}')\n")
                guide.append(f"async def get_{metric.lower()}_histogram() -> Dict[str, Any]:\n")
                guide.append(f"    '''Get {metric} histogram statistics'''\n")
                guide.append(f"    # TODO: Implement histogram reading\n")
                guide.append(f"    return {{\n")
                guide.append(f"        'metric': '{metric}',\n")
                guide.append(f"        'count': 0,\n")
                guide.append(f"        'sum': 0.0,\n")
                guide.append(f"        'buckets': [],\n")
                guide.append(f"        'quantiles': {{'p50': 0, 'p95': 0, 'p99': 0}}\n")
                guide.append(f"    }}\n")
            guide.append("```\n\n")

            if notes:
                guide.append(f"**Notes**: {notes}\n\n")

        return "".join(guide)


def main():
    """Run implementation tracking and reporting"""
    tracker = ImplementationTracker()

    print("🔍 Scanning telemetry implementation status...")
    tracker.update_implementation_status()

    print("\n📊 Generating implementation report...")
    report = tracker.get_implementation_report()

    print("\n" + "=" * 80)
    print("TELEMETRY IMPLEMENTATION STATUS")
    print("=" * 80)

    print(f"\n📈 Overall Progress:")
    print(f"  Total Endpoints: {report['overall']['total']}")
    print(f"  Implemented: {report['overall']['implemented']} ({report['overall']['completion_rate']:.1f}%)")
    print(f"  Partial: {report['overall']['partial']}")
    print(f"  Not Implemented: {report['overall']['not_implemented']}")

    print(f"\n🎯 By Priority:")
    for p in report["by_priority"]:
        print(f"  {p['priority']}: {p['implemented']}/{p['total']} ({p['completion_rate']:.1f}%)")

    print(f"\n📦 Top Modules by Mission-Critical Completion:")
    for m in report["by_module"][:5]:
        if m["mission_critical_total"] > 0:
            mc_rate = m["mission_critical_done"] / m["mission_critical_total"] * 100
            print(
                f"  {m['module']}: {m['mission_critical_done']}/{m['mission_critical_total']} mission-critical ({mc_rate:.1f}%)"
            )

    print(f"\n🚀 Next to Implement (Mission-Critical First):")
    for endpoint in report["next_to_implement"][:10]:
        print(f"  [{endpoint['priority']}] {endpoint['module']}: {endpoint['metric']}")
        print(f"    → {endpoint['endpoint']}")

    # Generate implementation guide for top priority
    if report["next_to_implement"]:
        top_module = report["next_to_implement"][0]["module"]
        guide = tracker.generate_implementation_guide(top_module)

        guide_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/implementation_guide.md")
        guide_path.write_text(guide)
        print(f"\n📝 Implementation guide saved to: {guide_path}")

    return report


if __name__ == "__main__":
    main()
