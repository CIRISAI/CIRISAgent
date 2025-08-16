#!/usr/bin/env python3
"""
Main orchestrator for comprehensive telemetry verification.
Runs all scanners and produces unified report answering:
1. Is it in the logic? (450-550 metrics expected)
2. Is it in production? (TSDB, memory, logs)
3. Is it available via API? (health, service status, telemetry endpoints)
4. Is it accessible via SDK? (TypeScript/Python client methods)
"""

import asyncio
import json
import sqlite3

# Add verification module to path
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).parent))

from verification.api_scanner import APIMetricScanner
from verification.enhanced_code_scanner import EnhancedCodeScanner
from verification.production_scanner import ProductionMetricScanner
from verification.schemas import MetricSource, MetricVerification, ScannerConfig, VerificationReport, VerificationStatus
from verification.sdk_scanner import SDKMetricScanner


class TelemetryVerificationOrchestrator:
    """Orchestrates all scanners and produces unified report."""

    def __init__(self, config: ScannerConfig):
        self.config = config
        self.all_metrics: Dict[str, MetricVerification] = {}
        self.report = VerificationReport(timestamp=datetime.now(), version="1.4.2")

    async def run_verification(self):
        """Run all verification scanners."""
        print("=" * 80)
        print("🔍 COMPREHENSIVE TELEMETRY VERIFICATION")
        print("=" * 80)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Version: 1.4.2")
        print()

        # 1. Scan code (using enhanced scanner for 540 metrics)
        print("📝 Phase 1: Scanning Code (Enhanced - 540 metrics)...")
        code_scanner = EnhancedCodeScanner(self.config)
        code_results = await code_scanner.scan(self.config)
        self._merge_results(code_results, "CODE")
        print(f"   Found {len(code_results)} metrics in code")

        # 2. Scan production
        print("\n🏭 Phase 2: Scanning Production...")
        prod_scanner = ProductionMetricScanner(self.config)
        prod_results = await prod_scanner.scan(self.config)
        self._merge_results(prod_results, "PRODUCTION")
        print(f"   Found {len(prod_results)} metrics in production")

        # 3. Scan API
        print("\n🌐 Phase 3: Scanning API...")
        try:
            api_scanner = APIMetricScanner(self.config)
            api_results = await api_scanner.scan(self.config)
            self._merge_results(api_results, "API")
            print(f"   Found {len(api_results)} metrics via API")
        except Exception as e:
            print(f"   ⚠️  API scan failed: {e}")
            api_results = []

        # 4. Scan SDK
        print("\n📦 Phase 4: Scanning SDK...")
        sdk_scanner = SDKMetricScanner(self.config)
        sdk_results = await sdk_scanner.scan(self.config)
        self._merge_results(sdk_results, "SDK")
        print(f"   Found {len(sdk_results)} metrics via SDK")

        # Generate report
        self._generate_statistics()
        self._save_to_database()
        self._generate_reports()

    def _merge_results(self, verifications: List[MetricVerification], source: str):
        """Merge verification results from a scanner."""
        for verification in verifications:
            metric_name = verification.metric_name

            if metric_name not in self.all_metrics:
                self.all_metrics[metric_name] = verification
            else:
                # Merge with existing verification
                existing = self.all_metrics[metric_name]

                # Merge code locations
                existing.code_locations.extend(verification.code_locations)

                # Merge production evidence
                existing.production_evidence.extend(verification.production_evidence)

                # Update flags
                existing.is_in_code = existing.is_in_code or verification.is_in_code
                existing.is_in_production = existing.is_in_production or verification.is_in_production
                existing.is_in_api = existing.is_in_api or verification.is_in_api
                existing.is_in_sdk = existing.is_in_sdk or verification.is_in_sdk

                # Update status
                if existing.is_in_code and existing.is_in_production:
                    existing.status = VerificationStatus.VERIFIED
                elif existing.is_in_code:
                    existing.status = VerificationStatus.FOUND_CODE
                elif existing.is_in_production:
                    existing.status = VerificationStatus.FOUND_PROD

    def _generate_statistics(self):
        """Generate statistics for the report."""
        self.report.total_metrics = len(self.all_metrics)

        for metric in self.all_metrics.values():
            if metric.is_in_code:
                self.report.in_code += 1
            if metric.is_in_production:
                # Check specific production sources
                for evidence in metric.production_evidence:
                    if evidence.source == MetricSource.TSDB_NODE:
                        self.report.in_tsdb += 1
                        break

            if metric.is_in_api:
                self.report.in_api += 1
            if metric.is_in_sdk:
                self.report.in_sdk += 1

            # Update verification counts
            if metric.status == VerificationStatus.VERIFIED:
                self.report.verified_metrics += 1
            elif metric.status == VerificationStatus.FOUND_CODE:
                self.report.code_only_metrics += 1
            elif metric.status == VerificationStatus.FOUND_PROD:
                self.report.prod_only_metrics += 1

    def _save_to_database(self):
        """Save results to SQLite database."""
        db_path = Path(self.config.reality_db)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create comprehensive table
        cursor.execute("DROP TABLE IF EXISTS metric_verification")
        cursor.execute(
            """
            CREATE TABLE metric_verification (
                metric_name TEXT PRIMARY KEY,
                module TEXT,
                version TEXT,
                status TEXT,
                is_in_code BOOLEAN,
                is_in_production BOOLEAN,
                is_in_api BOOLEAN,
                is_in_sdk BOOLEAN,
                code_locations INTEGER,
                production_sources TEXT,
                api_endpoints TEXT,
                sdk_methods TEXT,
                data_points INTEGER,
                first_seen TIMESTAMP,
                last_verified TIMESTAMP,
                notes TEXT
            )
        """
        )

        for metric_name, verification in self.all_metrics.items():
            # Aggregate production sources
            prod_sources = list(set(e.source.value for e in verification.production_evidence))
            api_endpoints = list(set(e.endpoint for e in verification.production_evidence if e.endpoint))
            sdk_methods = list(
                set(
                    e.endpoint
                    for e in verification.production_evidence
                    if e.source == MetricSource.SDK_METHOD and e.endpoint
                )
            )

            # Get total data points
            data_points = sum(e.data_points for e in verification.production_evidence if e.data_points)

            cursor.execute(
                """
                INSERT INTO metric_verification VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metric_name,
                    verification.module,
                    verification.version,
                    verification.status.value,
                    verification.is_in_code,
                    verification.is_in_production,
                    verification.is_in_api,
                    verification.is_in_sdk,
                    len(verification.code_locations),
                    json.dumps(prod_sources),
                    json.dumps(api_endpoints),
                    json.dumps(sdk_methods),
                    data_points,
                    verification.first_seen.isoformat() if verification.first_seen else None,
                    datetime.now().isoformat(),
                    verification.notes,
                ),
            )

        conn.commit()
        conn.close()

    def _generate_reports(self):
        """Generate various report formats."""
        # Summary report
        print("\n" + "=" * 80)
        print("📊 VERIFICATION SUMMARY")
        print("=" * 80)

        print(f"\n🎯 Overall Statistics:")
        print(f"  Total unique metrics found: {self.report.total_metrics}")
        print(f"  Fully verified (code + prod): {self.report.verified_metrics}")
        print(f"  Code only: {self.report.code_only_metrics}")
        print(f"  Production only: {self.report.prod_only_metrics}")

        print(f"\n📍 Location Breakdown:")
        print(f"  In code (logic/): {self.report.in_code}")
        print(f"  In TSDB nodes: {self.report.in_tsdb}")
        print(f"  Available via API: {self.report.in_api}")
        print(f"  Accessible via SDK: {self.report.in_sdk}")

        # Coverage analysis
        print(f"\n📈 Coverage Analysis:")
        if self.report.total_metrics > 0:
            code_coverage = (self.report.in_code / self.report.total_metrics) * 100
            api_coverage = (self.report.in_api / self.report.total_metrics) * 100
            sdk_coverage = (self.report.in_sdk / self.report.total_metrics) * 100
            verification_rate = (self.report.verified_metrics / self.report.total_metrics) * 100

            print(f"  Code coverage: {code_coverage:.1f}%")
            print(f"  API coverage: {api_coverage:.1f}%")
            print(f"  SDK coverage: {sdk_coverage:.1f}%")
            print(f"  Verification rate: {verification_rate:.1f}%")

        # Module breakdown
        print(f"\n📦 Module Breakdown:")
        module_counts = defaultdict(int)
        for metric in self.all_metrics.values():
            if metric.module:
                module_counts[metric.module] += 1

        for module, count in sorted(module_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {module:20} {count:3} metrics")

        # Top verified metrics
        print(f"\n✅ Sample Verified Metrics:")
        verified = [m for m in self.all_metrics.values() if m.status == VerificationStatus.VERIFIED]
        for metric in verified[:10]:
            sources = len(metric.production_evidence)
            print(f"  {metric.metric_name:40} ({sources} sources)")

        # Metrics needing attention
        print(f"\n⚠️  Metrics Needing Attention:")
        code_only = [m for m in self.all_metrics.values() if m.status == VerificationStatus.FOUND_CODE]
        if code_only:
            print(f"  Code-only metrics (not in production): {len(code_only)}")
            for metric in code_only[:5]:
                print(f"    - {metric.metric_name}")

        prod_only = [m for m in self.all_metrics.values() if m.status == VerificationStatus.FOUND_PROD]
        if prod_only:
            print(f"  Production-only metrics (not in code): {len(prod_only)}")
            for metric in prod_only[:5]:
                print(f"    - {metric.metric_name}")

        # Save detailed report
        self._save_detailed_report()

    def _save_detailed_report(self):
        """Save detailed report to file."""
        report_path = Path("TELEMETRY_VERIFICATION_REPORT.json")

        report_data = {
            "timestamp": self.report.timestamp.isoformat(),
            "version": self.report.version,
            "summary": {
                "total_metrics": self.report.total_metrics,
                "verified": self.report.verified_metrics,
                "code_only": self.report.code_only_metrics,
                "prod_only": self.report.prod_only_metrics,
                "in_code": self.report.in_code,
                "in_tsdb": self.report.in_tsdb,
                "in_api": self.report.in_api,
                "in_sdk": self.report.in_sdk,
            },
            "metrics": {},
        }

        for metric_name, verification in self.all_metrics.items():
            report_data["metrics"][metric_name] = {
                "status": verification.status.value,
                "module": verification.module,
                "version": verification.version,
                "in_code": verification.is_in_code,
                "in_production": verification.is_in_production,
                "in_api": verification.is_in_api,
                "in_sdk": verification.is_in_sdk,
                "code_locations": len(verification.code_locations),
                "production_sources": [e.source.value for e in verification.production_evidence],
                "data_points": sum(e.data_points for e in verification.production_evidence if e.data_points),
            }

        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2)

        print(f"\n💾 Detailed report saved to: {report_path}")
        print(f"💾 Database saved to: {self.config.reality_db}")

    def answer_questions(self):
        """Answer the specific questions asked."""
        print("\n" + "=" * 80)
        print("🎯 ANSWERING YOUR QUESTIONS")
        print("=" * 80)

        print("\n1️⃣ Is it in the logic? (Expected: 450-550 metrics)")
        print(f"   Answer: Found {self.report.in_code} metrics in code")
        if self.report.in_code >= 450 and self.report.in_code <= 550:
            print(f"   ✅ Within expected range!")
        elif self.report.in_code > 550:
            print(f"   📈 Above expected range - comprehensive coverage achieved")
        else:
            print(f"   ⚠️  Below expected range.")

        print("\n2️⃣ Is it in production? (TSDB, memory, logs)")
        print(f"   Answer: {self.report.in_tsdb} metrics in TSDB nodes")
        print(f"   Total in production: {self.report.verified_metrics + self.report.prod_only_metrics}")

        print("\n3️⃣ Is it available via API?")
        print(f"   Answer: {self.report.in_api} metrics accessible via API endpoints")

        print("\n4️⃣ Is it accessible via SDK?")
        print(f"   Answer: {self.report.in_sdk} metrics accessible via SDK methods")


async def main():
    """Main entry point."""
    config = ScannerConfig(
        base_path="/home/emoore/CIRISAgent/ciris_engine",
        api_base_url="http://localhost:8000/api/datum/v1",
        reality_db="telemetry_reality_comprehensive.db",
    )

    orchestrator = TelemetryVerificationOrchestrator(config)
    await orchestrator.run_verification()
    orchestrator.answer_questions()

    print("\n✅ VERIFICATION COMPLETE")


if __name__ == "__main__":
    asyncio.run(main())
