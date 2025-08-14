#!/usr/bin/env python3
"""
Test script for CIRIS SDK telemetry methods.
Tests both existing endpoints and newly added telemetry methods.
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List

# Import the SDK
sys.path.insert(0, "ciris_sdk")
from ciris_sdk.client import CIRISClient
from ciris_sdk.exceptions import CIRISAPIError, CIRISError


class TelemetryTester:
    """Test harness for SDK telemetry methods."""

    def __init__(self, base_url: str, api_key: str):
        self.client = CIRISClient(base_url=base_url, api_key=api_key, timeout=30.0)
        self.results = {"passed": [], "failed": [], "skipped": []}

    async def test_endpoint(self, name: str, method, *args, **kwargs):
        """Test a single endpoint method."""
        try:
            print(f"Testing {name}...", end=" ")
            result = await method(*args, **kwargs)

            # Basic validation
            if result is None:
                self.results["failed"].append({"name": name, "error": "Returned None"})
                print("❌ FAILED (None response)")
            else:
                self.results["passed"].append({"name": name, "has_data": bool(result)})
                print(f"✅ PASSED (data: {type(result).__name__})")
                return result

        except CIRISAPIError as e:
            if e.status_code == 404:
                self.results["skipped"].append({"name": name, "reason": "Endpoint not implemented (404)"})
                print("⚠️  SKIPPED (not implemented)")
            else:
                self.results["failed"].append({"name": name, "error": f"HTTP {e.status_code}: {e.message}"})
                print(f"❌ FAILED (HTTP {e.status_code})")
        except Exception as e:
            self.results["failed"].append({"name": name, "error": str(e)})
            print(f"❌ FAILED ({type(e).__name__})")

        return None

    async def run_tests(self):
        """Run all telemetry tests."""
        async with self.client:
            print("=" * 60)
            print("CIRIS SDK TELEMETRY TESTING")
            print("=" * 60)

            # System endpoints (should work)
            print("\n📊 SYSTEM TELEMETRY")
            print("-" * 40)

            await self.test_endpoint("system.health", self.client.system.health)
            await self.test_endpoint("system.time", self.client.system.time)
            await self.test_endpoint("system.resources", self.client.system.resources)
            await self.test_endpoint("system.services", self.client.system.services)

            # Core telemetry endpoints (should work)
            print("\n📈 CORE TELEMETRY")
            print("-" * 40)

            await self.test_endpoint("telemetry.overview", self.client.telemetry.get_overview)
            await self.test_endpoint("telemetry.metrics", self.client.telemetry.get_metrics)
            await self.test_endpoint("telemetry.traces", self.client.telemetry.get_traces, limit=5)
            await self.test_endpoint("telemetry.logs", self.client.telemetry.get_logs, limit=10)
            await self.test_endpoint("telemetry.resources", self.client.telemetry.resources)
            await self.test_endpoint("telemetry.resources_history", self.client.telemetry.resources_history, hours=1)

            # Memory endpoints (should work)
            print("\n🧠 MEMORY TELEMETRY")
            print("-" * 40)

            # Memory doesn't have stats method, skip for now
            await self.test_endpoint("memory.timeline", self.client.memory.timeline, hours=1)

            # Audit endpoints
            print("\n🔒 AUDIT TELEMETRY")
            print("-" * 40)

            await self.test_endpoint("audit.entries", self.client.audit.entries, limit=5)

            # New telemetry endpoints (may not be implemented yet)
            print("\n🆕 EXTENDED TELEMETRY")
            print("-" * 40)

            await self.test_endpoint("telemetry.service_registry", self.client.telemetry.get_service_registry)
            await self.test_endpoint("telemetry.llm_usage", self.client.telemetry.get_llm_usage)
            await self.test_endpoint("telemetry.circuit_breakers", self.client.telemetry.get_circuit_breakers)
            await self.test_endpoint(
                "telemetry.security_incidents", self.client.telemetry.get_security_incidents, hours=24
            )
            await self.test_endpoint("telemetry.handlers", self.client.telemetry.get_handlers)
            await self.test_endpoint("telemetry.errors", self.client.telemetry.get_errors, hours=1)
            await self.test_endpoint("telemetry.rate_limits", self.client.telemetry.get_rate_limits)
            await self.test_endpoint("telemetry.tsdb_status", self.client.telemetry.get_tsdb_status)
            await self.test_endpoint("telemetry.discord_status", self.client.telemetry.get_discord_status)
            await self.test_endpoint(
                "telemetry.aggregates_hourly", self.client.telemetry.get_aggregates_hourly, hours=1
            )
            await self.test_endpoint("telemetry.summary_daily", self.client.telemetry.get_summary_daily)
            await self.test_endpoint("telemetry.history", self.client.telemetry.get_telemetry_history, days=1)
            await self.test_endpoint("telemetry.backups", self.client.telemetry.get_backups)

            # Special format endpoints
            print("\n🔧 SPECIAL FORMAT TELEMETRY")
            print("-" * 40)

            # Test export (JSON format)
            await self.test_endpoint(
                "telemetry.export_json",
                self.client.telemetry.export_telemetry,
                format="json",
                start=datetime.now() - timedelta(hours=1),
                end=datetime.now(),
            )

            # Test Prometheus metrics
            await self.test_endpoint("telemetry.prometheus", self.client.telemetry.get_prometheus_metrics)

            self.print_summary()

    def print_summary(self):
        """Print test summary."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        total = len(self.results["passed"]) + len(self.results["failed"]) + len(self.results["skipped"])

        print(f"Total Tests:    {total}")
        print(f"✅ Passed:      {len(self.results['passed'])}")
        print(f"❌ Failed:      {len(self.results['failed'])}")
        print(f"⚠️  Skipped:     {len(self.results['skipped'])}")

        if self.results["passed"]:
            success_rate = (len(self.results["passed"]) / total) * 100
            print(f"Success Rate:   {success_rate:.1f}%")

        if self.results["failed"]:
            print("\nFailed Tests:")
            for test in self.results["failed"]:
                print(f"  - {test['name']}: {test['error']}")

        if self.results["skipped"]:
            print("\nSkipped Tests (Not Implemented):")
            for test in self.results["skipped"]:
                print(f"  - {test['name']}: {test['reason']}")

        # Write detailed report
        with open("sdk_telemetry_test_report.json", "w") as f:
            json.dump(self.results, f, indent=2, default=str)
        print("\nDetailed report saved to: sdk_telemetry_test_report.json")


async def main():
    """Main test runner."""
    # Test against production
    BASE_URL = "https://agents.ciris.ai/api/datum"
    API_KEY = "admin:ciris_admin_password"

    print(f"Testing SDK against: {BASE_URL}")
    print(f"Using auth: {'***' if API_KEY else 'None'}\n")

    tester = TelemetryTester(BASE_URL, API_KEY)
    await tester.run_tests()


if __name__ == "__main__":
    asyncio.run(main())
