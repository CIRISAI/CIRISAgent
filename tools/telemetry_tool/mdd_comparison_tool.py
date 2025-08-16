#!/usr/bin/env python3
"""
Mission-Driven Development (MDD) Tool
Compares the ~343 actual metrics with 485 documented metrics by module
"""

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from core.database import TelemetryDatabase
from core.doc_parser import TelemetryDocParser


class MDDComparisonTool:
    """Compare actual vs documented metrics for mission-driven development"""

    def __init__(self):
        self.db_path = Path(__file__).parent / "telemetry.db"
        self.db = TelemetryDatabase(self.db_path)
        self.parser = TelemetryDocParser()

    def get_actual_metrics(self) -> Dict[str, Set[str]]:
        """Get the ~343 actual metrics organized by module"""
        metrics_by_module = defaultdict(set)

        # 1. Handler action metrics (33)
        action_types = [
            "observe",
            "speak",
            "tool",
            "reject",
            "ponder",
            "defer",
            "memorize",
            "recall",
            "forget",
            "task_complete",
        ]
        for action in action_types:
            metrics_by_module["HANDLER_ACTIONS"].add(f"handler_invoked_{action}")
            metrics_by_module["HANDLER_ACTIONS"].add(f"handler_completed_{action}")
            metrics_by_module["HANDLER_ACTIONS"].add(f"handler_error_{action}")
        metrics_by_module["HANDLER_ACTIONS"].update(
            ["handler_invoked_total", "handler_completed_total", "handler_error_total"]
        )

        # 2. LLM Bus metrics (17 metrics as documented)
        metrics_by_module["LLM_BUS"].update(
            [
                "total_requests",
                "failed_requests",
                "total_latency_ms",
                "average_latency_ms",
                "consecutive_failures",
                "last_request_time",
                "last_failure_time",
                "circuit_breaker_state",
                "failure_count",
                "success_count",
                "tokens_used",
                "tokens_input",
                "tokens_output",
                "cost_cents",
                "carbon_grams",
                "energy_kwh",
                "round_robin_index",
            ]
        )

        # LLM Service specific metrics (separate from bus)
        metrics_by_module["LLM_SERVICE"].update(
            [
                "llm_tokens_used",
                "llm_api_call_structured",
                "availability",
                "health_status",
                "uptime_seconds",
                "error_count",
                "request_count",
            ]
        )

        # 3. Memory Bus metrics (2 as documented)
        metrics_by_module["MEMORY_BUS"].update(["operation_count", "service_availability"])

        # Memory Service specific metrics
        metrics_by_module["MEMORY_SERVICE"].update(
            [
                "graph_node_count",
                "secrets_enabled",
                "storage_backend",
                "uptime_seconds",
                "request_count",
                "error_count",
                "error_rate",
                "healthy",
                "nodes_created",
                "edges_created",
                "nodes_by_type",
                "correlations_count",
                "time_series_points",
            ]
        )

        # 4. Communication-specific metrics (4)
        metrics_by_module["COMMUNICATION_BUS"].update(
            ["messages_processed", "messages_queued", "queue_size", "processing_latency_ms"]
        )

        # 5. Common service metrics (applied to all 23 services)
        common_metrics = ["availability", "health_status", "uptime_seconds", "error_count", "request_count"]

        services = [
            "MEMORY_SERVICE",
            "CONFIG_SERVICE",
            "TELEMETRY_SERVICE",
            "AUDIT_SERVICE",
            "INCIDENT_SERVICE",
            "TSDB_CONSOLIDATION_SERVICE",
            "TIME_SERVICE",
            "SHUTDOWN_SERVICE",
            "INITIALIZATION_SERVICE",
            "AUTHENTICATION_SERVICE",
            "RESOURCE_MONITOR_SERVICE",
            "DATABASE_MAINTENANCE_SERVICE",
            "SECRETS_SERVICE",
            "WISE_AUTHORITY_SERVICE",
            "ADAPTIVE_FILTER_SERVICE",
            "VISIBILITY_SERVICE",
            "SELF_OBSERVATION_SERVICE",
            "LLM_SERVICE",
            "RUNTIME_CONTROL_SERVICE",
            "TASK_SCHEDULER_SERVICE",
            "SECRETS_TOOL_SERVICE",
            "SERVICE_REGISTRY",
            "PROCESSING_QUEUE",
        ]

        for service in services:
            for metric in common_metrics:
                metrics_by_module[service].add(metric)

        # 6. Telemetry overview metrics (25)
        metrics_by_module["TELEMETRY_OVERVIEW"].update(
            [
                "uptime_seconds",
                "cognitive_state",
                "messages_processed_24h",
                "thoughts_processed_24h",
                "tasks_completed_24h",
                "errors_24h",
                "tokens_last_hour",
                "cost_last_hour_cents",
                "carbon_last_hour_grams",
                "energy_last_hour_kwh",
                "tokens_24h",
                "cost_24h_cents",
                "carbon_24h_grams",
                "energy_24h_kwh",
                "memory_mb",
                "cpu_percent",
                "healthy_services",
                "degraded_services",
                "error_rate_percent",
                "current_task",
                "reasoning_depth",
                "active_deferrals",
                "recent_incidents",
                "total_metrics",
                "active_services",
            ]
        )

        # 7. Adapter-specific metrics
        metrics_by_module["DISCORD_ADAPTER"].update(
            ["messages_received", "messages_sent", "discord_latency_ms", "active_guilds", "active_channels"]
        )

        metrics_by_module["API_ADAPTER"].update(
            ["http_requests", "response_time_ms", "active_connections", "websocket_connections"]
        )

        metrics_by_module["CLI_ADAPTER"].update(["commands_processed", "cli_sessions"])

        return dict(metrics_by_module)

    def get_documented_metrics(self) -> Dict[str, Set[str]]:
        """Get the 485 documented metrics from .md files"""
        modules = self.parser.parse_all_docs()

        metrics_by_module = {}
        for module in modules:
            module_name = module["module_name"]
            metrics = set()

            for metric in module.get("metrics", []):
                metric_name = metric.get("metric_name", "")
                if metric_name:
                    metrics.add(metric_name)

            if metrics:
                metrics_by_module[module_name] = metrics

        return metrics_by_module

    def compare_metrics(self) -> Dict:
        """Compare actual vs documented metrics"""
        actual = self.get_actual_metrics()
        documented = self.get_documented_metrics()

        # Calculate totals
        actual_total = sum(len(m) for m in actual.values())
        documented_total = sum(len(m) for m in documented.values())

        # Find overlaps and gaps
        all_modules = set(actual.keys()) | set(documented.keys())

        comparison_by_module = {}
        for module in sorted(all_modules):
            actual_metrics = actual.get(module, set())
            doc_metrics = documented.get(module, set())

            comparison_by_module[module] = {
                "actual_count": len(actual_metrics),
                "documented_count": len(doc_metrics),
                "in_both": len(actual_metrics & doc_metrics),
                "only_actual": len(actual_metrics - doc_metrics),
                "only_documented": len(doc_metrics - actual_metrics),
                "coverage_percent": (len(actual_metrics & doc_metrics) / len(doc_metrics) * 100 if doc_metrics else 0),
                "implementation_percent": (
                    len(actual_metrics & doc_metrics) / len(actual_metrics) * 100 if actual_metrics else 0
                ),
            }

        # Get mission scores from database
        mission_scores = self.get_mission_scores()

        return {
            "summary": {
                "actual_total": actual_total,
                "documented_total": documented_total,
                "actual_modules": len(actual),
                "documented_modules": len(documented),
            },
            "by_module": comparison_by_module,
            "mission_scores": mission_scores,
            "recommendations": self.generate_recommendations(comparison_by_module, mission_scores),
        }

    def get_mission_scores(self) -> Dict[str, float]:
        """Get GPT-5 mission alignment scores from JSON file"""
        scores_file = Path(__file__).parent / "scores" / "gpt-5" / "semantic_scores.json"

        if not scores_file.exists():
            return {}

        with scores_file.open() as f:
            data = json.load(f)

        scores = {}
        for item in data:
            module_name = item["module_name"]
            mission_score = item.get("mission_alignment_score", 0.5)
            scores[module_name] = mission_score

        return scores

    def generate_recommendations(self, comparison: Dict, scores: Dict) -> List[Dict]:
        """Generate implementation recommendations based on mission alignment"""
        recommendations = []

        for module, stats in comparison.items():
            if stats["only_documented"] > 0:
                mission_score = scores.get(module, 0.5)

                if mission_score >= 0.7:  # High mission alignment
                    priority = "HIGH"
                elif mission_score >= 0.5:
                    priority = "MEDIUM"
                else:
                    priority = "LOW"

                recommendations.append(
                    {
                        "module": module,
                        "priority": priority,
                        "mission_score": mission_score,
                        "metrics_to_implement": stats["only_documented"],
                        "reason": f"Module has {stats['only_documented']} documented metrics not yet implemented",
                    }
                )

        # Sort by priority and mission score
        recommendations.sort(key=lambda x: (-x["mission_score"], x["module"]))

        return recommendations[:10]  # Top 10 recommendations


def main():
    """Run the MDD comparison"""
    tool = MDDComparisonTool()

    print("=" * 80)
    print("MISSION-DRIVEN DEVELOPMENT METRIC COMPARISON")
    print("Comparing ~343 Actual vs 485 Documented Metrics")
    print("=" * 80)

    results = tool.compare_metrics()

    print(
        f"""
📊 SUMMARY:
  • Actual metrics: {results['summary']['actual_total']}
  • Documented metrics: {results['summary']['documented_total']}
  • Actual modules: {results['summary']['actual_modules']}
  • Documented modules: {results['summary']['documented_modules']}
"""
    )

    print("📈 MODULE-BY-MODULE COMPARISON:")
    print(f"{'Module':<30} {'Actual':>8} {'Docs':>8} {'Both':>8} {'Coverage':>10}")
    print("-" * 66)

    for module, stats in sorted(results["by_module"].items()):
        if stats["actual_count"] > 0 or stats["documented_count"] > 0:
            print(
                f"{module:<30} {stats['actual_count']:>8} {stats['documented_count']:>8} "
                f"{stats['in_both']:>8} {stats['coverage_percent']:>9.1f}%"
            )

    print("\n🎯 TOP IMPLEMENTATION PRIORITIES (by Mission Alignment):")
    for i, rec in enumerate(results["recommendations"][:5], 1):
        print(f"\n{i}. {rec['module']} [{rec['priority']}]")
        print(f"   Mission Score: {rec['mission_score']:.2f}")
        print(f"   Metrics to implement: {rec['metrics_to_implement']}")
        print(f"   {rec['reason']}")

    # Save results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/mdd_comparison_results.json")
    with output_file.open("w") as f:
        json.dump(results, f, indent=2, default=list)

    print(f"\n📁 Full results saved to: {output_file}")

    print("\n" + "=" * 80)
    print("KEY INSIGHT")
    print("=" * 80)
    print(
        f"""
The actual implementation ({results['summary']['actual_total']} metrics) represents
the CORE operational metrics needed for the system to function.

The documented metrics ({results['summary']['documented_total']}) include both
current metrics AND planned enhancements for deeper observability.

Focus implementation on high mission-alignment modules first!
"""
    )


if __name__ == "__main__":
    main()
