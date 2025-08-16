#!/usr/bin/env python3
"""
Reality check: Compare our 128 identified metrics against what's ACTUALLY in production.
Also finds metrics in production that we DIDN'T identify.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

import aiohttp


class RealityChecker:
    """Check what metrics are REALLY in production."""

    def __init__(self):
        # Load our 128 identified metrics
        with open("comprehensive_metrics.json", "r") as f:
            data = json.load(f)
            self.our_metrics = set(data["metrics"])

        # Storage for production metrics
        self.production_metrics = set()
        self.api_metrics = set()
        self.unknown_metrics = set()  # In production but not in our list

    async def check_production_api(self):
        """Check what metrics are available via API."""

        token = "21131fdf6cd5a44044fcec261aba2c596aa8fad1a5b9725a41cacf6b33419023"
        headers = {"Authorization": f"Bearer service:{token}"}

        async with aiohttp.ClientSession(headers=headers) as session:
            # Check health endpoint
            url = "https://agents.ciris.ai/api/datum/v1/system/health"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Extract metrics from health
                        if "data" in data:
                            health_data = data["data"]

                            # System metrics
                            if "uptime_seconds" in health_data:
                                self.api_metrics.add("system.uptime_seconds")

                            # Service availability metrics
                            if "services" in health_data:
                                for service_name, service_data in health_data["services"].items():
                                    if isinstance(service_data, dict):
                                        if "available" in service_data:
                                            metric = f"{service_name}.available"
                                            self.api_metrics.add(metric)
                                        if "healthy" in service_data:
                                            metric = f"{service_name}.healthy"
                                            self.api_metrics.add(metric)
            except Exception as e:
                print(f"Error checking API: {e}")

    def check_known_production_metrics(self):
        """Add metrics we KNOW are in production from previous investigations."""

        known_in_prod = [
            # From TSDB investigation
            "llm.tokens.total",
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "llm.latency.ms",
            # Handler metrics we know are recorded
            "handler_invoked_total",
            "handler_completed_total",
            "handler_invoked_task_complete",
            "handler_invoked_memorize",
            "handler_completed_task_complete",
            "handler_completed_memorize",
            # Action metrics
            "action_selected_task_complete",
            "action_selected_memorize",
            # Processing metrics
            "thought_processing_started",
            "thought_processing_completed",
            # Others
            "llm_tokens_used",
            "llm_api_call_structured",
            "error.occurred",
            "telemetry_service.shutdown",
        ]

        self.production_metrics.update(known_in_prod)

    def analyze_gaps(self) -> Dict[str, any]:
        """Analyze gaps between what we identified and what's in production."""

        # Metrics in our list that ARE in production
        confirmed = self.our_metrics & (self.production_metrics | self.api_metrics)

        # Metrics in our list but NOT in production
        not_in_prod = self.our_metrics - (self.production_metrics | self.api_metrics)

        # Metrics in production but NOT in our list
        self.unknown_metrics = (self.production_metrics | self.api_metrics) - self.our_metrics

        return {
            "confirmed": confirmed,
            "not_in_production": not_in_prod,
            "unknown_in_production": self.unknown_metrics,
            "our_total": len(self.our_metrics),
            "production_total": len(self.production_metrics | self.api_metrics),
            "confirmed_count": len(confirmed),
            "not_in_prod_count": len(not_in_prod),
            "unknown_count": len(self.unknown_metrics),
        }

    async def check_tsdb_patterns(self):
        """Check for TSDB node patterns we might have missed."""

        # These are patterns we see in production but might not have identified
        potential_patterns = [
            # Environmental metrics with different naming
            "llm.environmental.*",
            "*.environmental.*",
            # System metrics we might have missed
            "system.cpu_percent",
            "system.memory_mb",
            "system.disk_used_gb",
            "system.network_bytes_sent",
            # Service-specific patterns
            "*.latency.ms",
            "*.throughput",
            "*.queue_size",
            "*.circuit_breaker_*",
            # Correlation metrics
            "correlation.*.count",
            "correlation.*.latency",
        ]

        # Add any that match these patterns to unknown if not in our list
        for pattern in potential_patterns:
            if "*" in pattern:
                # It's a pattern, check if we have similar metrics
                base = pattern.replace("*", "")
                # For now, just note it
                pass
            else:
                # It's a specific metric
                if pattern not in self.our_metrics:
                    self.unknown_metrics.add(pattern)

    async def generate_report(self) -> str:
        """Generate comprehensive reality check report."""

        # Run all checks
        await self.check_production_api()
        self.check_known_production_metrics()
        await self.check_tsdb_patterns()

        # Analyze gaps
        analysis = self.analyze_gaps()

        # Generate report
        report = []
        report.append("=" * 80)
        report.append("🔍 REALITY CHECK: 128 Metrics vs Production")
        report.append("=" * 80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("")

        report.append("📊 SUMMARY:")
        report.append(f"  Our identified metrics:        {analysis['our_total']}")
        report.append(f"  Metrics found in production:   {analysis['production_total']}")
        report.append(f"  Confirmed (in both):           {analysis['confirmed_count']}")
        report.append(f"  Not in production:             {analysis['not_in_prod_count']}")
        report.append(f"  Unknown (in prod, not in list): {analysis['unknown_count']}")
        report.append("")

        # Confirmation rate
        if analysis["our_total"] > 0:
            rate = (analysis["confirmed_count"] / analysis["our_total"]) * 100
            report.append(f"✅ CONFIRMATION RATE: {rate:.1f}%")
        report.append("")

        # Show confirmed metrics
        report.append("✅ CONFIRMED METRICS (in both our list and production):")
        for metric in sorted(analysis["confirmed"])[:20]:
            report.append(f"  - {metric}")
        if len(analysis["confirmed"]) > 20:
            report.append(f"  ... and {len(analysis['confirmed']) - 20} more")
        report.append("")

        # Show metrics not in production
        report.append("❌ NOT IN PRODUCTION (in our list but not found):")
        not_in_prod_sorted = sorted(analysis["not_in_production"])

        # Group by category
        handlers = [m for m in not_in_prod_sorted if m.startswith("handler_") or m.startswith("action_")]
        services = [
            m for m in not_in_prod_sorted if "." in m and not m.startswith("handler_") and not m.startswith("action_")
        ]
        others = [m for m in not_in_prod_sorted if m not in handlers and m not in services]

        if handlers:
            report.append("  Handler metrics not recorded:")
            for metric in handlers[:10]:
                report.append(f"    - {metric}")

        if services:
            report.append("  Service metrics not recorded:")
            for metric in services[:10]:
                report.append(f"    - {metric}")

        if others:
            report.append("  Other metrics not recorded:")
            for metric in others[:10]:
                report.append(f"    - {metric}")
        report.append("")

        # Show unknown metrics
        if analysis["unknown_in_production"]:
            report.append("🔍 UNKNOWN METRICS (in production but NOT in our list):")
            for metric in sorted(analysis["unknown_in_production"])[:20]:
                report.append(f"  - {metric}")
            report.append("")
            report.append("  ⚠️  These metrics exist in production but we didn't identify them!")
        report.append("")

        # Analysis
        report.append("📈 ANALYSIS:")
        if analysis["unknown_count"] > 0:
            report.append(f"  - Found {analysis['unknown_count']} metrics in production we didn't identify")
            report.append("  - Our scanner may be missing some metric patterns")

        if analysis["not_in_prod_count"] > 50:
            report.append(f"  - {analysis['not_in_prod_count']} identified metrics are not being recorded")
            report.append("  - Many handler and service metrics are defined but not active")

        return "\n".join(report), analysis


async def main():
    """Main entry point."""
    checker = RealityChecker()
    report, analysis = await checker.generate_report()
    print(report)

    # Save analysis
    with open("reality_check.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "our_metrics": len(checker.our_metrics),
                "production_metrics": len(checker.production_metrics | checker.api_metrics),
                "confirmed": analysis["confirmed_count"],
                "not_in_production": analysis["not_in_prod_count"],
                "unknown_in_production": analysis["unknown_count"],
                "unknown_metrics": sorted(checker.unknown_metrics),
            },
            f,
            indent=2,
        )

    print("💾 Saved analysis to reality_check.json")


if __name__ == "__main__":
    asyncio.run(main())
