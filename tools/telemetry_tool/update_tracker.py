#!/usr/bin/env python3
"""
Update the implementation tracker with get_metrics() progress.
Track which services have implemented _collect_custom_metrics(), and metric counts.
"""

import sqlite3
from datetime import datetime
from pathlib import Path


def update_tracker():
    """Update tracker with current get_metrics()/_collect_custom_metrics() status."""

    db_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/telemetry_mdd.db")

    # Check if DB exists, if not create it
    if not db_path.exists():
        print(f"Creating new tracker database at {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create tables
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS services (
                service_name TEXT PRIMARY KEY,
                service_type TEXT,
                has_custom_metrics INTEGER DEFAULT 0,
                metric_count INTEGER DEFAULT 0,
                implementation_status TEXT DEFAULT 'TODO',
                last_updated TIMESTAMP,
                notes TEXT
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT,
                metric_name TEXT,
                metric_type TEXT,  -- PULL or PUSH
                storage TEXT,      -- NONE or TSDB
                implementation_status TEXT DEFAULT 'TODO',
                last_updated TIMESTAMP,
                FOREIGN KEY (service_name) REFERENCES services(service_name)
            )
        """
        )
    else:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if our tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='services'")
        if not cursor.fetchone():
            cursor.execute(
                """
                CREATE TABLE services (
                    service_name TEXT PRIMARY KEY,
                    service_type TEXT,
                    has_custom_metrics INTEGER DEFAULT 0,
                    metric_count INTEGER DEFAULT 0,
                    implementation_status TEXT DEFAULT 'TODO',
                    last_updated TIMESTAMP,
                    notes TEXT
                )
            """
            )

    # Define all 21 services and their current status
    # has_custom_metrics: 1 if service has _collect_custom_metrics() implemented
    services = [
        # Graph Services (6)
        ("memory", "graph", 1, 5, "DONE"),  # Updated to use _collect_custom_metrics
        ("config", "graph", 1, 2, "IN_PROGRESS"),  # Has _collect_custom_metrics
        ("telemetry", "graph", 0, 0, "TODO"),
        ("audit", "graph", 0, 0, "TODO"),
        ("incident_management", "graph", 0, 0, "TODO"),  # Needs conversion
        ("tsdb_consolidation", "graph", 0, 0, "TODO"),
        # Infrastructure Services (7)
        ("time", "infrastructure", 0, 0, "TODO"),
        ("shutdown", "infrastructure", 0, 0, "TODO"),
        ("initialization", "infrastructure", 0, 0, "TODO"),
        ("authentication", "infrastructure", 0, 0, "TODO"),
        ("resource_monitor", "infrastructure", 0, 0, "TODO"),
        ("database_maintenance", "infrastructure", 0, 0, "TODO"),
        ("secrets", "infrastructure", 0, 0, "TODO"),
        # Governance Services (4)
        ("wise_authority", "governance", 0, 0, "TODO"),
        ("adaptive_filter", "governance", 0, 0, "TODO"),
        ("visibility", "governance", 0, 0, "TODO"),
        ("self_observation", "governance", 0, 0, "TODO"),
        # Runtime Services (3)
        ("llm", "runtime", 0, 0, "TODO"),
        ("runtime_control", "runtime", 0, 0, "TODO"),
        ("task_scheduler", "runtime", 0, 0, "TODO"),
        # Tool Services (1)
        ("secrets_tool", "tool", 1, 1, "TODO"),  # Has get_telemetry, needs conversion
    ]

    # Update services table
    for service_name, service_type, has_telemetry, metric_count, status in services:
        cursor.execute(
            """
            INSERT OR REPLACE INTO services
            (service_name, service_type, has_custom_metrics, metric_count, implementation_status, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (service_name, service_type, has_telemetry, metric_count, status, datetime.now()),
        )

    conn.commit()

    # Generate progress report
    cursor.execute(
        """
        SELECT
            service_type,
            COUNT(*) as total,
            SUM(has_custom_metrics) as implemented,
            SUM(metric_count) as total_metrics
        FROM services
        GROUP BY service_type
    """
    )

    print("=" * 60)
    print("GET_METRICS() IMPLEMENTATION PROGRESS - v1.4.3")
    print("=" * 60)
    print()

    for service_type, total, implemented, total_metrics in cursor.fetchall():
        pct = (implemented / total * 100) if total > 0 else 0
        print(f"{service_type.upper():20} {implemented}/{total} ({pct:.0f}%) - {total_metrics or 0} metrics")

    print()

    # Overall progress
    cursor.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(has_custom_metrics) as implemented,
            SUM(metric_count) as total_metrics
        FROM services
    """
    )

    total, implemented, total_metrics = cursor.fetchone()
    pct = (implemented / total * 100) if total > 0 else 0

    print(f"{'OVERALL':20} {implemented}/{total} ({pct:.0f}%) - {total_metrics} metrics")
    print()
    print(f"Services with _collect_custom_metrics(): {implemented}/{total} services")
    print(f"Metrics from these services: {total_metrics}")
    print()
    print("ACTUAL SYSTEM METRICS (from modular scanner):")
    print(f"  • PULL metrics: 82 (get_metrics + _collect_custom_metrics)")
    print(f"  • PUSH metrics: 19 (record_metric + memorize_metric)")
    print(f"  • Handler metrics: 44 (automatic from ActionDispatcher)")
    print(f"  • TOTAL: 136 metrics")
    print()
    print(f"Target:  250 metrics")
    print(f"Gap:     114 metrics")
    print()
    print("IMPLEMENTATION PLAN:")
    print(f"  • Phase 1: 5 high-value services × 12 metrics = 60")
    print(f"  • Phase 2: 6 runtime objects × 8 metrics = 48")
    print(f"  • Phase 3: Fill remaining ~10 metrics")
    print(f"  • Total new: 118 metrics → 254 total")
    print()

    # Show TODO services
    cursor.execute(
        """
        SELECT service_name, service_type
        FROM services
        WHERE has_custom_metrics = 0
        ORDER BY
            CASE service_type
                WHEN 'runtime' THEN 1
                WHEN 'governance' THEN 2
                WHEN 'graph' THEN 3
                WHEN 'infrastructure' THEN 4
                ELSE 5
            END
    """
    )

    todos = cursor.fetchall()
    if todos:
        print("SERVICES NEEDING _collect_custom_metrics():")
        print("-" * 40)
        for service_name, service_type in todos[:5]:
            print(f"  • {service_name:25} ({service_type})")
        if len(todos) > 5:
            print(f"  ... and {len(todos) - 5} more")

    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    update_tracker()
