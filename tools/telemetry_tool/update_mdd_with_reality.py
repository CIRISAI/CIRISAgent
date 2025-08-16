#!/usr/bin/env python3
"""
Update MDD tool database with reality-based telemetry metrics
- Mark implemented metrics as DONE
- Add 86 recommended metrics as TODO
- Generate comprehensive coverage report
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set


class MDDUpdater:
    """Update MDD database with accurate telemetry status"""

    def __init__(self):
        self.db_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/telemetry_mdd.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        # Create table if it doesn't exist
        self.create_tables()

        # Load analysis results
        self.final_analysis = self.load_json("final_metric_analysis.json")
        self.gap_analysis = self.load_json("gap_analysis_results.json")

    def create_tables(self):
        """Create the metrics table if it doesn't exist"""
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                implementation_status TEXT NOT NULL CHECK(implementation_status IN ('TODO', 'DONE', 'IN_PROGRESS')),
                priority TEXT CHECK(priority IN ('HIGH', 'MEDIUM', 'LOW')),
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(module_name, metric_name)
            )
        """
        )

        # Create index for better query performance
        self.cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_module_status
            ON metrics(module_name, implementation_status)
        """
        )

        self.conn.commit()

    def load_json(self, filename: str) -> Dict:
        """Load JSON data"""
        path = Path(f"/home/emoore/CIRISAgent/tools/telemetry_tool/{filename}")
        with path.open("r") as f:
            return json.load(f)

    def clear_existing_metrics(self):
        """Clear existing metrics to start fresh with accurate data"""
        print("Clearing existing metrics...")
        self.cursor.execute("DELETE FROM metrics")
        self.conn.commit()
        print("✓ Cleared existing metrics")

    def insert_metric(self, module: str, metric: str, status: str, priority: str = None):
        """Insert a metric into the database"""
        try:
            self.cursor.execute(
                """
                INSERT INTO metrics (module_name, metric_name, implementation_status, priority, notes)
                VALUES (?, ?, ?, ?, ?)
            """,
                (module, metric, status, priority, f"Updated from reality analysis {datetime.now().isoformat()}"),
            )
        except sqlite3.IntegrityError:
            # Update if exists
            self.cursor.execute(
                """
                UPDATE metrics
                SET implementation_status = ?, priority = ?, notes = ?
                WHERE module_name = ? AND metric_name = ?
            """,
                (status, priority, f"Updated from reality analysis {datetime.now().isoformat()}", module, metric),
            )

    def update_implemented_metrics(self):
        """Mark all actually implemented metrics as DONE"""
        print("\n📊 Updating implemented metrics...")

        total_implemented = 0
        for module_name, data in self.final_analysis.items():
            # Get metrics that are in both docs and code (implemented)
            implemented_metrics = data.get("in_both", [])

            # Also add metrics only in code (implemented but not documented)
            code_only_metrics = data.get("only_in_code", [])

            all_implemented = set(implemented_metrics) | set(code_only_metrics)

            for metric in all_implemented:
                self.insert_metric(module_name, metric, "DONE", "HIGH")
                total_implemented += 1

        self.conn.commit()
        print(f"✓ Marked {total_implemented} metrics as DONE")
        return total_implemented

    def add_recommended_todos(self):
        """Add the 86 recommended metrics as TODO"""
        print("\n📝 Adding recommended TODOs...")

        total_todos = 0
        for item in self.gap_analysis:
            module = item.get("module")
            priority = item.get("priority", "MEDIUM")
            top_3 = item.get("top_3_to_add", [])

            # Map semantic priority to MDD priority
            priority_map = {"CRITICAL": "HIGH", "IMPORTANT": "MEDIUM", "USEFUL": "LOW", "OPTIONAL": "LOW"}
            mdd_priority = priority_map.get(priority, "MEDIUM")

            for metric in top_3:
                self.insert_metric(module, metric, "TODO", mdd_priority)
                total_todos += 1

        self.conn.commit()
        print(f"✓ Added {total_todos} TODO metrics")
        return total_todos

    def generate_coverage_report(self):
        """Generate comprehensive coverage report"""
        print("\n" + "=" * 80)
        print("TELEMETRY COVERAGE REPORT - MISSION-DRIVEN DEVELOPMENT")
        print("=" * 80)

        # Get overall statistics
        self.cursor.execute(
            """
            SELECT
                implementation_status,
                COUNT(*) as count
            FROM metrics
            GROUP BY implementation_status
        """
        )

        status_counts = dict(self.cursor.fetchall())
        total_metrics = sum(status_counts.values())
        done_count = status_counts.get("DONE", 0)
        todo_count = status_counts.get("TODO", 0)

        print(f"\n📊 OVERALL STATISTICS")
        print(f"{'='*60}")
        print(f"Total Metrics Tracked: {total_metrics}")
        print(f"✅ Implemented (DONE): {done_count} ({done_count/total_metrics*100:.1f}%)")
        print(f"📝 Recommended (TODO): {todo_count} ({todo_count/total_metrics*100:.1f}%)")
        print(f"🎯 Coverage Rate: {done_count/(done_count+todo_count)*100:.1f}%")

        # Module-by-module breakdown
        print(f"\n📦 MODULE COVERAGE BREAKDOWN")
        print(f"{'='*60}")

        self.cursor.execute(
            """
            SELECT
                module_name,
                implementation_status,
                COUNT(*) as count
            FROM metrics
            GROUP BY module_name, implementation_status
            ORDER BY module_name
        """
        )

        module_data = {}
        for row in self.cursor.fetchall():
            module, status, count = row
            if module not in module_data:
                module_data[module] = {"DONE": 0, "TODO": 0}
            module_data[module][status] = count

        # Categories
        categories = {
            "Buses": ["LLM_BUS", "MEMORY_BUS", "COMMUNICATION_BUS", "WISE_BUS", "TOOL_BUS", "RUNTIME_CONTROL_BUS"],
            "Graph Services": [
                "MEMORY_SERVICE",
                "CONFIG_SERVICE",
                "TELEMETRY_SERVICE",
                "AUDIT_SERVICE",
                "INCIDENT_SERVICE",
                "TSDB_CONSOLIDATION_SERVICE",
            ],
            "Infrastructure": [
                "TIME_SERVICE",
                "SHUTDOWN_SERVICE",
                "INITIALIZATION_SERVICE",
                "AUTHENTICATION_SERVICE",
                "RESOURCE_MONITOR_SERVICE",
                "DATABASE_MAINTENANCE_SERVICE",
                "SECRETS_SERVICE",
            ],
            "Governance": [
                "WISE_AUTHORITY_SERVICE",
                "ADAPTIVE_FILTER_SERVICE",
                "VISIBILITY_SERVICE",
                "SELF_OBSERVATION_SERVICE",
            ],
            "Runtime": ["LLM_SERVICE", "RUNTIME_CONTROL_SERVICE", "TASK_SCHEDULER_SERVICE", "SECRETS_TOOL_SERVICE"],
            "Components": [
                "CIRCUIT_BREAKER_COMPONENT",
                "PROCESSING_QUEUE_COMPONENT",
                "SERVICE_REGISTRY_REGISTRY",
                "SERVICE_INITIALIZER_COMPONENT",
                "AGENT_PROCESSOR_PROCESSOR",
            ],
            "Adapters": ["DISCORD_ADAPTER", "API_ADAPTER", "CLI_ADAPTER"],
        }

        for category, modules in categories.items():
            print(f"\n🔹 {category}")
            print("-" * 50)

            for module in modules:
                if module in module_data:
                    done = module_data[module].get("DONE", 0)
                    todo = module_data[module].get("TODO", 0)
                    total = done + todo

                    if total > 0:
                        coverage = done / total * 100

                        # Status emoji based on coverage
                        if coverage >= 80:
                            status = "✅"
                        elif coverage >= 50:
                            status = "⚠️"
                        else:
                            status = "❌"

                        # Get match percentage from analysis
                        match_pct = 0
                        if module in self.final_analysis:
                            match_pct = self.final_analysis[module].get("match_percentage", 0)

                        print(
                            f"{status} {module:30} Done:{done:3} Todo:{todo:3} Coverage:{coverage:5.1f}% Match:{match_pct:5.1f}%"
                        )

        # Priority breakdown
        print(f"\n🎯 PRIORITY BREAKDOWN")
        print(f"{'='*60}")

        self.cursor.execute(
            """
            SELECT
                priority,
                implementation_status,
                COUNT(*) as count
            FROM metrics
            WHERE priority IS NOT NULL
            GROUP BY priority, implementation_status
            ORDER BY
                CASE priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                END
        """
        )

        priority_data = {}
        for row in self.cursor.fetchall():
            priority, status, count = row
            if priority not in priority_data:
                priority_data[priority] = {"DONE": 0, "TODO": 0}
            priority_data[priority][status] = count

        for priority in ["HIGH", "MEDIUM", "LOW"]:
            if priority in priority_data:
                done = priority_data[priority].get("DONE", 0)
                todo = priority_data[priority].get("TODO", 0)
                total = done + todo
                print(f"{priority:8} - Done: {done:3}, Todo: {todo:3}, Total: {total:3}")

        # Covenant alignment summary
        print(f"\n🔮 COVENANT ALIGNMENT")
        print(f"{'='*60}")
        print("Critical Gaps Being Addressed:")

        critical_modules = [item["module"] for item in self.gap_analysis if item.get("priority") == "CRITICAL"]
        for i, module in enumerate(critical_modules[:10], 1):  # Show top 10
            print(f"  {i}. {module}")

        if len(critical_modules) > 10:
            print(f"  ... and {len(critical_modules) - 10} more")

        print(f"\n📈 IMPLEMENTATION PROGRESS")
        print(f"{'='*60}")
        print(f"Original Documentation: 597 metrics")
        print(f"Actually Implemented: ~{done_count} metrics ({done_count/597*100:.1f}%)")
        print(f"Recommended to Add: {todo_count} metrics")
        print(f"Redundant/Skip: ~{597 - done_count - todo_count} metrics")

        # Save report to file
        report_path = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/TELEMETRY_COVERAGE_REPORT.md")
        self.save_markdown_report(report_path, status_counts, module_data, priority_data)
        print(f"\n📁 Report saved to: {report_path}")

    def save_markdown_report(self, path: Path, status_counts: Dict, module_data: Dict, priority_data: Dict):
        """Save detailed markdown report"""
        done_count = status_counts.get("DONE", 0)
        todo_count = status_counts.get("TODO", 0)
        total = done_count + todo_count

        content = f"""# Telemetry Coverage Report - Mission-Driven Development

Generated: {datetime.now().isoformat()}

## Executive Summary

**Coverage Achievement: {done_count/(done_count+todo_count)*100:.1f}%**

- ✅ **Implemented Metrics**: {done_count}
- 📝 **Recommended TODOs**: {todo_count}
- 🎯 **Total Tracked**: {total}
- 📊 **Original Documentation**: 597 metrics
- ♻️ **Redundant/Skippable**: ~{597 - total} metrics

## Key Findings

1. **Actual Implementation Rate**: ~{done_count/597*100:.1f}% of documented metrics are implemented
2. **Critical Gaps**: 23 modules need immediate attention
3. **Covenant Alignment**: 86 metrics recommended for addition to improve alignment
4. **Redundancy**: ~181 documented metrics are redundant with existing coverage

## Module Coverage Details

"""

        # Add module details
        categories = {
            "Buses": ["LLM_BUS", "MEMORY_BUS", "COMMUNICATION_BUS", "WISE_BUS", "TOOL_BUS", "RUNTIME_CONTROL_BUS"],
            "Graph Services": [
                "MEMORY_SERVICE",
                "CONFIG_SERVICE",
                "TELEMETRY_SERVICE",
                "AUDIT_SERVICE",
                "INCIDENT_SERVICE",
                "TSDB_CONSOLIDATION_SERVICE",
            ],
            "Infrastructure": [
                "TIME_SERVICE",
                "SHUTDOWN_SERVICE",
                "INITIALIZATION_SERVICE",
                "AUTHENTICATION_SERVICE",
                "RESOURCE_MONITOR_SERVICE",
                "DATABASE_MAINTENANCE_SERVICE",
                "SECRETS_SERVICE",
            ],
            "Governance": [
                "WISE_AUTHORITY_SERVICE",
                "ADAPTIVE_FILTER_SERVICE",
                "VISIBILITY_SERVICE",
                "SELF_OBSERVATION_SERVICE",
            ],
            "Runtime": ["LLM_SERVICE", "RUNTIME_CONTROL_SERVICE", "TASK_SCHEDULER_SERVICE", "SECRETS_TOOL_SERVICE"],
            "Components": [
                "CIRCUIT_BREAKER_COMPONENT",
                "PROCESSING_QUEUE_COMPONENT",
                "SERVICE_REGISTRY_REGISTRY",
                "SERVICE_INITIALIZER_COMPONENT",
                "AGENT_PROCESSOR_PROCESSOR",
            ],
            "Adapters": ["DISCORD_ADAPTER", "API_ADAPTER", "CLI_ADAPTER"],
        }

        for category, modules in categories.items():
            content += f"\n### {category}\n\n"
            content += "| Module | Done | Todo | Coverage | Status |\n"
            content += "|--------|------|------|----------|--------|\n"

            for module in modules:
                if module in module_data:
                    done = module_data[module].get("DONE", 0)
                    todo = module_data[module].get("TODO", 0)
                    total = done + todo

                    if total > 0:
                        coverage = done / total * 100

                        if coverage >= 80:
                            status = "✅ Good"
                        elif coverage >= 50:
                            status = "⚠️ Partial"
                        else:
                            status = "❌ Critical"

                        content += f"| {module} | {done} | {todo} | {coverage:.1f}% | {status} |\n"

        content += f"""

## Priority Analysis

| Priority | Done | Todo | Total |
|----------|------|------|-------|
"""

        for priority in ["HIGH", "MEDIUM", "LOW"]:
            if priority in priority_data:
                done = priority_data[priority].get("DONE", 0)
                todo = priority_data[priority].get("TODO", 0)
                total = done + todo
                content += f"| {priority} | {done} | {todo} | {total} |\n"

        content += f"""

## Next Steps

1. **Immediate (Week 1)**: Implement metrics for 4 services with 0% coverage
2. **Short-term (Week 2-3)**: Add critical metrics for 23 modules
3. **Medium-term (Month 1)**: Complete important metrics for 7 modules
4. **Long-term**: Update documentation to reflect implementation decisions

## Mission Alignment

All recommended metrics align with Meta-Goal M-1 (Adaptive Coherence) and support:
- **Beneficence**: Metrics that ensure positive impact
- **Non-maleficence**: Error tracking and resilience metrics
- **Transparency**: Operational visibility and audit trails
- **Autonomy**: User interaction and decision metrics
- **Justice**: Fair resource allocation and access metrics
- **Coherence**: System integration and consistency metrics
"""

        path.write_text(content)

    def run(self):
        """Execute the update process"""
        print("🚀 Starting MDD Database Update with Reality Data")
        print("=" * 60)

        # Clear and rebuild with accurate data
        self.clear_existing_metrics()

        # Update with real implementation status
        implemented_count = self.update_implemented_metrics()

        # Add recommended TODOs
        todo_count = self.add_recommended_todos()

        # Generate comprehensive report
        self.generate_coverage_report()

        print(f"\n✅ MDD Database Updated Successfully!")
        print(f"   - {implemented_count} metrics marked as DONE")
        print(f"   - {todo_count} metrics added as TODO")
        print(f"   - Coverage: {implemented_count/(implemented_count+todo_count)*100:.1f}%")

        self.conn.close()


if __name__ == "__main__":
    updater = MDDUpdater()
    updater.run()
