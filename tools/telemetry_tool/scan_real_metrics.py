#!/usr/bin/env python3
"""
Module-by-module scanner for REAL metrics in production.
This is the single source of truth - it scans code and verifies against production.
"""

import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple


class RealMetricsScanner:
    """Scan for actual metrics in code, module by module."""

    def __init__(self):
        self.base_path = Path("/home/emoore/CIRISAgent/ciris_engine")
        self.db_path = Path("telemetry_reality.db")
        self.init_database()

    def init_database(self):
        """Create a clean database for reality tracking."""
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()

        # Drop old table if exists - fresh start
        self.cursor.execute("DROP TABLE IF EXISTS real_metrics")

        # Create new reality-based table
        self.cursor.execute(
            """
            CREATE TABLE real_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name TEXT NOT NULL,
                metric_pattern TEXT NOT NULL,
                production_name TEXT,
                file_path TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                code_context TEXT,
                is_dynamic BOOLEAN DEFAULT 0,
                is_verified BOOLEAN DEFAULT 0,
                data_points INTEGER DEFAULT 0,
                last_seen TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(module_name, metric_pattern, file_path, line_number)
            )
        """
        )
        self.conn.commit()

    def scan_file_for_metrics(self, file_path: Path) -> List[Dict]:
        """Scan a single file for all metric patterns."""
        metrics = []

        try:
            with open(file_path, "r") as f:
                content = f.read()
                lines = content.split("\n")

            # Pattern 1: Direct memorize_metric calls
            patterns = [
                (r'memorize_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']', False),
                (r'memorize_metric\s*\(\s*["\']([^"\']+)["\']', False),
                (r'\.memorize_metric\s*\(\s*["\']([^"\']+)["\']', False),
                # Pattern 2: record_metric calls
                (r'record_metric\s*\(\s*["\']([^"\']+)["\']', False),
                (r'\.record_metric\s*\(\s*["\']([^"\']+)["\']', False),
                # Pattern 3: Dynamic f-string metrics
                (r'record_metric\s*\(\s*f["\']([^"\']+)["\']', True),
                (r'memorize_metric\s*\(\s*f["\']([^"\']+)["\']', True),
                # Pattern 4: Variable-based metrics
                (r'metric_name\s*=\s*["\']([^"\']+)["\']', False),
            ]

            for pattern, is_dynamic in patterns:
                for match in re.finditer(pattern, content):
                    line_num = content[: match.start()].count("\n") + 1
                    metric_name = match.group(1)

                    # Get context (3 lines before and after)
                    start_line = max(0, line_num - 3)
                    end_line = min(len(lines), line_num + 3)
                    context = "\n".join(lines[start_line:end_line])

                    # For dynamic metrics, try to resolve the pattern
                    if is_dynamic and "{" in metric_name:
                        # Extract the base and variable parts
                        parts = re.split(r"[{}]", metric_name)
                        base = parts[0]
                        var = parts[1] if len(parts) > 1 else "variable"

                        # Look for common variable names
                        if var == "service_name":
                            # Generate common service names
                            for service in ["llm", "memory", "telemetry", "audit"]:
                                metrics.append(
                                    {
                                        "pattern": f"{base}{service}",
                                        "production_name": f"{base}{service}",
                                        "is_dynamic": True,
                                        "line": line_num,
                                        "context": context,
                                    }
                                )
                        elif var == "key":
                            metrics.append(
                                {
                                    "pattern": f"{base}*",
                                    "production_name": None,  # Will be resolved later
                                    "is_dynamic": True,
                                    "line": line_num,
                                    "context": context,
                                }
                            )
                        else:
                            metrics.append(
                                {
                                    "pattern": metric_name,
                                    "production_name": None,
                                    "is_dynamic": True,
                                    "line": line_num,
                                    "context": context,
                                }
                            )
                    else:
                        metrics.append(
                            {
                                "pattern": metric_name,
                                "production_name": metric_name,
                                "is_dynamic": is_dynamic,
                                "line": line_num,
                                "context": context,
                            }
                        )

        except Exception as e:
            print(f"Error scanning {file_path}: {e}")

        return metrics

    def scan_module(self, module_name: str, module_path: Path) -> int:
        """Scan a module and store results in database."""
        print(f"\n📦 Scanning {module_name}...")

        if module_path.is_file():
            files = [module_path]
        else:
            files = list(module_path.rglob("*.py"))

        total_metrics = 0
        unique_patterns = set()

        for file_path in files:
            if "__pycache__" in str(file_path):
                continue

            metrics = self.scan_file_for_metrics(file_path)

            for metric in metrics:
                try:
                    self.cursor.execute(
                        """
                        INSERT OR IGNORE INTO real_metrics
                        (module_name, metric_pattern, production_name, file_path,
                         line_number, code_context, is_dynamic)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            module_name,
                            metric["pattern"],
                            metric["production_name"],
                            str(file_path).replace(str(self.base_path), "..."),
                            metric["line"],
                            metric["context"],
                            metric["is_dynamic"],
                        ),
                    )
                    unique_patterns.add(metric["pattern"])
                    total_metrics += 1
                except sqlite3.IntegrityError:
                    pass  # Duplicate, skip

        self.conn.commit()

        if total_metrics > 0:
            print(f"  ✅ Found {total_metrics} metric calls")
            print(f"  📊 Unique patterns: {len(unique_patterns)}")

            # Show examples
            self.cursor.execute(
                """
                SELECT DISTINCT metric_pattern, is_dynamic
                FROM real_metrics
                WHERE module_name = ?
                LIMIT 5
            """,
                (module_name,),
            )

            for pattern, is_dynamic in self.cursor.fetchall():
                dynamic_flag = " (dynamic)" if is_dynamic else ""
                print(f"     - {pattern}{dynamic_flag}")

        else:
            print(f"  ❌ No metrics found")

        return total_metrics

    def scan_all_modules(self):
        """Scan all modules systematically."""
        print("=" * 80)
        print("🔍 MODULE-BY-MODULE METRIC SCANNING")
        print("=" * 80)

        modules = {
            # Core Services
            "LLM_SERVICE": self.base_path / "logic/services/runtime/llm_service.py",
            "MEMORY_SERVICE": self.base_path / "logic/services/graph/memory_service.py",
            "TELEMETRY_SERVICE": self.base_path / "logic/services/graph/telemetry_service.py",
            "AUDIT_SERVICE": self.base_path / "logic/services/graph/audit_service.py",
            "CONFIG_SERVICE": self.base_path / "logic/services/graph/config_service.py",
            "INCIDENT_SERVICE": self.base_path / "logic/services/graph/incident_service.py",
            "TSDB_SERVICE": self.base_path / "logic/services/graph/tsdb_consolidation_service.py",
            # Infrastructure
            "AUTH_SERVICE": self.base_path / "logic/services/infrastructure/authentication.py",
            "RESOURCE_MONITOR": self.base_path / "logic/services/infrastructure/resource_monitor.py",
            "TIME_SERVICE": self.base_path / "logic/services/infrastructure/time.py",
            "SHUTDOWN_SERVICE": self.base_path / "logic/services/infrastructure/shutdown.py",
            "INIT_SERVICE": self.base_path / "logic/services/infrastructure/initialization.py",
            # Governance
            "WISE_AUTHORITY": self.base_path / "logic/services/governance/wise_authority.py",
            "ADAPTIVE_FILTER": self.base_path / "logic/services/governance/filter.py",
            "VISIBILITY": self.base_path / "logic/services/governance/visibility.py",
            "SELF_OBSERVATION": self.base_path / "logic/services/governance/self_observation.py",
            # Runtime
            "TASK_SCHEDULER": self.base_path / "logic/services/runtime/scheduler.py",
            # Handlers & Infrastructure
            "HANDLERS": self.base_path / "logic/infrastructure/handlers",
            "BUSES": self.base_path / "logic/buses",
            "ADAPTERS": self.base_path / "logic/adapters",
        }

        total_found = 0
        modules_with_metrics = 0

        for module_name, module_path in modules.items():
            if module_path.exists():
                count = self.scan_module(module_name, module_path)
                total_found += count
                if count > 0:
                    modules_with_metrics += 1
            else:
                print(f"\n⚠️  {module_name}: Path not found ({module_path})")

        print("\n" + "=" * 80)
        print(f"📊 SCAN SUMMARY")
        print(f"  Total modules scanned: {len(modules)}")
        print(f"  Modules with metrics: {modules_with_metrics}")
        print(f"  Total metric calls found: {total_found}")

    def verify_against_production(self):
        """Verify found metrics against known production metrics."""
        print("\n" + "=" * 80)
        print("🔄 VERIFYING AGAINST PRODUCTION")
        print("=" * 80)

        # Known production metrics (from our earlier investigation)
        known_production = {
            "llm.tokens.total",
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "llm.latency.ms",
            "llm_tokens_used",
            "llm_api_call_structured",
            "thought_processing_completed",
            "thought_processing_started",
            "handler_invoked_total",
            "handler_completed_total",
            "handler_invoked_task_complete",
            "handler_invoked_memorize",
            "handler_completed_task_complete",
            "handler_completed_memorize",
            "action_selected_task_complete",
            "action_selected_memorize",
            "error.occurred",
        }

        # Get all patterns from database
        self.cursor.execute("SELECT DISTINCT metric_pattern FROM real_metrics")
        found_patterns = {row[0] for row in self.cursor.fetchall()}

        # Mark verified metrics
        verified_count = 0
        for prod_metric in known_production:
            # Check direct match
            if prod_metric in found_patterns:
                self.cursor.execute(
                    """
                    UPDATE real_metrics
                    SET is_verified = 1, production_name = ?
                    WHERE metric_pattern = ?
                """,
                    (prod_metric, prod_metric),
                )
                verified_count += 1
            else:
                # Check if it's a dynamic pattern match
                for pattern in found_patterns:
                    if "*" in pattern:
                        base = pattern.replace("*", "")
                        if prod_metric.startswith(base):
                            self.cursor.execute(
                                """
                                UPDATE real_metrics
                                SET is_verified = 1, production_name = ?
                                WHERE metric_pattern = ?
                            """,
                                (prod_metric, pattern),
                            )
                            verified_count += 1
                            break

        self.conn.commit()

        print(f"✅ Verified {verified_count} metrics exist in production")

        # Show verification results
        self.cursor.execute(
            """
            SELECT module_name, COUNT(*) as total,
                   SUM(is_verified) as verified
            FROM real_metrics
            GROUP BY module_name
            ORDER BY verified DESC
        """
        )

        print("\n📊 Verification by Module:")
        for module, total, verified in self.cursor.fetchall():
            percentage = (verified / total * 100) if total > 0 else 0
            status = "✅" if percentage > 50 else "⚠️" if percentage > 0 else "❌"
            print(f"  {status} {module:20} {verified}/{total} verified ({percentage:.1f}%)")

    def generate_report(self):
        """Generate final report."""
        print("\n" + "=" * 80)
        print("📋 FINAL REPORT")
        print("=" * 80)

        # Get summary stats
        self.cursor.execute(
            """
            SELECT
                COUNT(DISTINCT module_name) as modules,
                COUNT(*) as total_metrics,
                SUM(is_verified) as verified,
                SUM(is_dynamic) as dynamic
            FROM real_metrics
        """
        )

        modules, total, verified, dynamic = self.cursor.fetchone()

        print(f"  Modules with metrics: {modules}")
        print(f"  Total metric calls: {total}")
        print(f"  Verified in production: {verified}")
        print(f"  Dynamic metrics: {dynamic}")
        print(f"  Verification rate: {verified/total*100:.1f}%")

        print(f"\n💾 Database saved to: {self.db_path}")
        print("   Use this as the single source of truth!")


def main():
    """Main entry point."""
    print("🚀 REAL METRICS SCANNER - SYSTEMATIC MODULE-BY-MODULE ANALYSIS")
    print("=" * 80)

    scanner = RealMetricsScanner()
    scanner.scan_all_modules()
    scanner.verify_against_production()
    scanner.generate_report()

    print("\n✅ SCAN COMPLETE - Reality captured in telemetry_reality.db")


if __name__ == "__main__":
    main()
