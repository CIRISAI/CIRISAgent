#!/usr/bin/env python3
"""
Track enterprise telemetry implementation progress
Shows current phase and next steps
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Tuple


class ImplementationTracker:
    """Track implementation progress by phase"""

    PHASES = {
        1: "Foundation - Service Telemetry Methods",
        2: "Bus Integration - Parallel Collection",
        3: "Aggregator - Enterprise Collection",
        4: "API Routes - Enterprise Endpoints",
        5: "Integration - Wire Everything Together",
        6: "Testing - Validation and Performance",
        7: "Documentation - API and Usage",
        8: "Monitoring - Production Integration",
    }

    def __init__(self):
        self.db_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/telemetry_mdd.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

    def get_phase_for_task(self, module: str, metric: str) -> int:
        """Determine which phase a task belongs to"""
        if "SERVICE" in module and "telemetry" in metric:
            return 1
        elif "BUS" in module:
            return 2
        elif module == "TELEMETRY_AGGREGATOR":
            return 3
        elif "API" in module:
            return 4
        elif module in ["SERVICE_REGISTRY", "TELEMETRY_SERVICE"]:
            return 5
        elif "TEST" in module:
            return 6
        elif "DOC" in module or "GUIDE" in module:
            return 7
        elif any(x in module for x in ["GRAFANA", "PROMETHEUS", "ALERT"]):
            return 8
        else:
            return 1  # Default to foundation

    def get_phase_status(self) -> dict:
        """Get completion status for each phase"""

        # Get all TODO tasks
        self.cursor.execute(
            """
            SELECT module_name, metric_name, priority
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

        todos = self.cursor.fetchall()

        # Get all DONE tasks
        self.cursor.execute(
            """
            SELECT module_name, metric_name
            FROM metrics
            WHERE implementation_status = 'DONE'
        """
        )

        done = self.cursor.fetchall()

        # Organize by phase
        phase_stats = {}
        for phase_num, phase_name in self.PHASES.items():
            phase_stats[phase_num] = {
                "name": phase_name,
                "todo": [],
                "done": [],
                "high_priority": 0,
                "medium_priority": 0,
                "low_priority": 0,
            }

        # Categorize TODOs
        for module, metric, priority in todos:
            phase = self.get_phase_for_task(module, metric)
            phase_stats[phase]["todo"].append((module, metric, priority))

            if priority == "HIGH":
                phase_stats[phase]["high_priority"] += 1
            elif priority == "MEDIUM":
                phase_stats[phase]["medium_priority"] += 1
            else:
                phase_stats[phase]["low_priority"] += 1

        # Count DONE (simplified - not phase-specific for existing metrics)
        total_done = len(done)

        return phase_stats, total_done

    def print_progress_report(self):
        """Print detailed progress report"""

        phase_stats, total_done = self.get_phase_status()

        print("\n" + "=" * 80)
        print("🚀 ENTERPRISE TELEMETRY IMPLEMENTATION TRACKER")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Overall progress
        total_todos = sum(len(p["todo"]) for p in phase_stats.values())
        overall_progress = total_done / (total_done + total_todos) * 100 if (total_done + total_todos) > 0 else 0

        print(f"\n📊 OVERALL PROGRESS: {overall_progress:.1f}%")
        print(f"   ✅ Completed: {total_done} tasks")
        print(f"   📝 Remaining: {total_todos} tasks")

        # Phase-by-phase breakdown
        print("\n" + "=" * 80)
        print("PHASE BREAKDOWN")
        print("=" * 80)

        for phase_num in sorted(phase_stats.keys()):
            stats = phase_stats[phase_num]
            todo_count = len(stats["todo"])

            if todo_count > 0:
                # Determine phase status
                if phase_num == 1 and stats["high_priority"] > 0:
                    status = "🔴 BLOCKED"
                elif all(
                    p < phase_num for p, s in phase_stats.items() if len(s["todo"]) > 0 and s["high_priority"] > 0
                ):
                    status = "🟡 READY"
                else:
                    status = "⏸️  WAITING"

                print(f"\n{status} Phase {phase_num}: {stats['name']}")
                print("-" * 60)
                print(
                    f"Tasks: HIGH:{stats['high_priority']:2} MED:{stats['medium_priority']:2} LOW:{stats['low_priority']:2} | Total:{todo_count:2}"
                )

                # Show first few HIGH priority tasks
                high_tasks = [t for t in stats["todo"] if t[2] == "HIGH"][:3]
                if high_tasks:
                    print("Next HIGH priority tasks:")
                    for module, metric, _ in high_tasks:
                        print(f"  • {module}: {metric}")

        # Current focus
        print("\n" + "=" * 80)
        print("🎯 CURRENT FOCUS")
        print("=" * 80)

        # Find first phase with HIGH priority tasks
        for phase_num in sorted(phase_stats.keys()):
            stats = phase_stats[phase_num]
            if stats["high_priority"] > 0:
                print(f"\nPhase {phase_num}: {stats['name']}")
                print(f"Complete these {stats['high_priority']} HIGH priority tasks first:")
                print()

                for module, metric, priority in stats["todo"]:
                    if priority == "HIGH":
                        # Get task notes
                        self.cursor.execute(
                            """
                            SELECT notes FROM metrics
                            WHERE module_name = ? AND metric_name = ?
                        """,
                            (module, metric),
                        )
                        notes = self.cursor.fetchone()
                        notes_text = notes[0] if notes else ""

                        print(f"  📌 {module}: {metric}")
                        if notes_text:
                            print(f"     → {notes_text[:80]}...")
                        print()
                break

        # Next steps
        print("=" * 80)
        print("📋 IMPLEMENTATION STEPS")
        print("=" * 80)
        print(
            """
1. START WITH FOUNDATION (Phase 1):
   - Add get_telemetry() to 4 services with 0% coverage
   - Standardize telemetry methods in components

2. THEN BUS INTEGRATION (Phase 2):
   - Add parallel collection to buses
   - Implement caching for static metrics

3. BUILD AGGREGATOR (Phase 3):
   - Create TelemetryAggregator class
   - Implement parallel collection logic
   - Add covenant scoring

4. CREATE API ROUTES (Phase 4):
   - Implement unified /telemetry endpoint
   - Add view filters and formatters
   - Create health check endpoint

5. INTEGRATE & TEST (Phases 5-6):
   - Wire everything together
   - Test parallel collection performance
   - Validate covenant scoring

Bottom-up approach ensures each layer is solid before building the next!
"""
        )

    def mark_complete(self, module: str, metric: str):
        """Mark a task as complete"""
        self.cursor.execute(
            """
            UPDATE metrics
            SET implementation_status = 'DONE'
            WHERE module_name = ? AND metric_name = ?
        """,
            (module, metric),
        )
        self.conn.commit()
        print(f"✅ Marked as DONE: {module} - {metric}")

    def get_next_task(self) -> Tuple[str, str, str]:
        """Get the next HIGH priority task to work on"""
        self.cursor.execute(
            """
            SELECT module_name, metric_name, notes
            FROM metrics
            WHERE implementation_status = 'TODO' AND priority = 'HIGH'
            ORDER BY module_name, metric_name
            LIMIT 1
        """
        )

        result = self.cursor.fetchone()
        if result:
            return result

        # No HIGH priority, get MEDIUM
        self.cursor.execute(
            """
            SELECT module_name, metric_name, notes
            FROM metrics
            WHERE implementation_status = 'TODO' AND priority = 'MEDIUM'
            ORDER BY module_name, metric_name
            LIMIT 1
        """
        )

        result = self.cursor.fetchone()
        return result if result else (None, None, None)


def main():
    tracker = ImplementationTracker()

    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "next":
            module, metric, notes = tracker.get_next_task()
            if module:
                print(f"\n📌 NEXT TASK:")
                print(f"Module: {module}")
                print(f"Task: {metric}")
                if notes:
                    print(f"Details: {notes}")
            else:
                print("✅ All tasks complete!")

        elif sys.argv[1] == "done" and len(sys.argv) > 3:
            tracker.mark_complete(sys.argv[2], sys.argv[3])
            tracker.print_progress_report()

        else:
            print("Usage:")
            print("  python track_implementation.py         # Show progress")
            print("  python track_implementation.py next    # Get next task")
            print("  python track_implementation.py done MODULE METRIC  # Mark complete")
    else:
        tracker.print_progress_report()


if __name__ == "__main__":
    main()
