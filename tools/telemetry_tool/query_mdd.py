#!/usr/bin/env python3
"""
Query the MDD telemetry database for quick status checks
"""

import sqlite3
import sys
from pathlib import Path


def query_database(query_type="summary", module=None):
    """Query the telemetry MDD database"""

    db_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/telemetry_mdd.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if query_type == "summary":
        # Overall summary
        cursor.execute(
            """
            SELECT
                implementation_status,
                COUNT(*) as count
            FROM metrics
            GROUP BY implementation_status
        """
        )
        print("\n📊 OVERALL METRICS STATUS")
        print("=" * 40)
        for status, count in cursor.fetchall():
            print(f"{status:12} : {count:4} metrics")

        # Coverage calculation
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN implementation_status = 'DONE' THEN 1 ELSE 0 END) as done,
                COUNT(*) as total
            FROM metrics
        """
        )
        done, total = cursor.fetchone()
        print(f"\n🎯 Coverage   : {done}/{total} = {done/total*100:.1f}%")

    elif query_type == "todos":
        # List all TODOs by priority
        cursor.execute(
            """
            SELECT
                module_name,
                metric_name,
                priority
            FROM metrics
            WHERE implementation_status = 'TODO'
            ORDER BY
                CASE priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                END,
                module_name, metric_name
        """
        )

        print("\n📝 TODO METRICS")
        print("=" * 60)
        current_priority = None
        for module, metric, priority in cursor.fetchall():
            if priority != current_priority:
                print(f"\n{priority or 'UNSET'} Priority:")
                print("-" * 40)
                current_priority = priority
            print(f"  {module:30} : {metric}")

    elif query_type == "critical":
        # Show modules with lowest coverage
        cursor.execute(
            """
            SELECT
                module_name,
                SUM(CASE WHEN implementation_status = 'DONE' THEN 1 ELSE 0 END) as done,
                SUM(CASE WHEN implementation_status = 'TODO' THEN 1 ELSE 0 END) as todo,
                COUNT(*) as total
            FROM metrics
            GROUP BY module_name
            HAVING todo > 0
            ORDER BY (done * 1.0 / total) ASC
            LIMIT 10
        """
        )

        print("\n❌ CRITICAL MODULES (Lowest Coverage)")
        print("=" * 60)
        print(f"{'Module':<35} {'Done':>5} {'Todo':>5} {'Coverage':>10}")
        print("-" * 60)
        for module, done, todo, total in cursor.fetchall():
            coverage = done / total * 100 if total > 0 else 0
            print(f"{module:<35} {done:5} {todo:5} {coverage:9.1f}%")

    elif query_type == "module" and module:
        # Show specific module details
        cursor.execute(
            """
            SELECT
                metric_name,
                implementation_status,
                priority
            FROM metrics
            WHERE module_name = ?
            ORDER BY implementation_status, metric_name
        """,
            (module,),
        )

        results = cursor.fetchall()
        if results:
            print(f"\n📦 MODULE: {module}")
            print("=" * 60)

            done_metrics = [m for m, s, p in results if s == "DONE"]
            todo_metrics = [(m, p) for m, s, p in results if s == "TODO"]

            print(f"\n✅ DONE ({len(done_metrics)} metrics):")
            for metric in done_metrics:
                print(f"  • {metric}")

            if todo_metrics:
                print(f"\n📝 TODO ({len(todo_metrics)} metrics):")
                for metric, priority in todo_metrics:
                    print(f"  • {metric} [{priority or 'UNSET'}]")

            coverage = len(done_metrics) / len(results) * 100 if results else 0
            print(f"\n🎯 Coverage: {coverage:.1f}%")
        else:
            print(f"Module '{module}' not found in database")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        query_database("summary")
    elif sys.argv[1] == "todos":
        query_database("todos")
    elif sys.argv[1] == "critical":
        query_database("critical")
    elif sys.argv[1] == "module" and len(sys.argv) > 2:
        query_database("module", sys.argv[2])
    else:
        print("Usage:")
        print("  python query_mdd.py           # Overall summary")
        print("  python query_mdd.py todos     # List all TODO metrics")
        print("  python query_mdd.py critical  # Show critical modules")
        print("  python query_mdd.py module MODULE_NAME  # Show specific module")
