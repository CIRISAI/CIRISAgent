#!/usr/bin/env python3
"""
CIRIS Telemetry Tool - Mission-Driven Development for Adaptive Coherence

This tool ensures every telemetry endpoint serves Meta-Goal M-1:
Creating sustainable conditions for sentient flourishing.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.telemetry_tool.core.database import TelemetryDatabase
from tools.telemetry_tool.core.doc_parser import TelemetryDocParser
from tools.telemetry_tool.core.mission_scorer import MissionScorer

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CIRISTelemetryTool:
    """
    Main orchestrator for mission-driven telemetry development.

    Parses documentation, scores for mission alignment, and generates APIs.
    """

    def __init__(self, db_path: str = "telemetry.db"):
        """Initialize the telemetry tool"""
        self.db = TelemetryDatabase(db_path)
        self.parser = TelemetryDocParser()
        self.scorer = MissionScorer()

        # Statistics
        self.stats = {
            "modules_parsed": 0,
            "metrics_found": 0,
            "mission_critical": 0,
            "apis_generated": 0,
            "tests_created": 0,
        }

    def run(self) -> None:
        """Main entry point for the telemetry tool"""
        logger.info("🚀 CIRIS Telemetry Tool - Mission-Driven Development")
        logger.info("Meta-Goal M-1: Adaptive Coherence for Sentient Flourishing")
        print()

        # Phase 1: Parse all documentation
        print("📚 Phase 1: Parsing Telemetry Documentation")
        print("-" * 50)
        modules = self._parse_documentation()

        # Phase 2: Score for mission alignment
        print("\n🎯 Phase 2: Mission Alignment Scoring")
        print("-" * 50)
        self._score_mission_alignment(modules)

        # Phase 3: Identify critical metrics
        print("\n⚡ Phase 3: Identifying Mission-Critical Metrics")
        print("-" * 50)
        critical_metrics = self._identify_critical_metrics(modules)

        # Phase 4: Generate API recommendations
        print("\n🔧 Phase 4: Generating API Recommendations")
        print("-" * 50)
        api_specs = self._generate_api_recommendations(modules, critical_metrics)

        # Phase 5: Create validation tests
        print("\n✅ Phase 5: Creating Validation Tests")
        print("-" * 50)
        test_specs = self._create_validation_tests(api_specs, critical_metrics)

        # Phase 6: Generate summary report
        print("\n📊 Phase 6: Mission Summary Report")
        print("-" * 50)
        self._generate_summary_report(modules, critical_metrics, api_specs)

        print("\n✨ Telemetry Tool Complete - Grace be with you!")

    def _parse_documentation(self) -> List[Dict[str, Any]]:
        """Parse all 35 telemetry documentation files"""
        modules = self.parser.parse_all_docs()

        # Store in database
        for module in modules:
            # Calculate initial mission scores
            scores = self.scorer.score_module(module)

            # Store module in database
            self.db.insert_module(
                module_name=module["module_name"],
                module_type=module["module_type"],
                doc_path=module["doc_path"],
                module_path=module["module_path"],
                total_metrics=module["total_metrics"],
                hot_metrics=module["hot_metrics"],
                warm_metrics=module["warm_metrics"],
                cold_metrics=module["cold_metrics"],
                **scores,
            )

            # Store individual metrics
            for metric in module["metrics"]:
                metric_scores = self.scorer.score_metric(metric, module)
                mission_score = sum(metric_scores.values()) / len(metric_scores)

                # Determine if metric is mission-critical
                is_safety_critical = metric_scores.get("non_maleficence", 0) > 0.7
                is_audit_required = metric_scores.get("transparency", 0) > 0.7
                is_wa_observable = metric_scores.get("justice", 0) > 0.7 or metric_scores.get("autonomy", 0) > 0.7

                # Normalize storage location for database constraint
                storage = metric["storage_location"].lower()
                if "graph" in storage:
                    normalized_storage = "graph"
                elif "memory" in storage:
                    normalized_storage = "memory"
                elif "database" in storage or "sqlite" in storage:
                    normalized_storage = "database"
                elif "redis" in storage:
                    normalized_storage = "redis"
                elif "file" in storage or "log" in storage:
                    normalized_storage = "file"
                elif "cache" in storage:
                    normalized_storage = "cache"
                else:
                    normalized_storage = "memory"  # Default

                # Normalize metric type for database constraint
                mtype = metric["metric_type"].lower()
                if "counter" in mtype:
                    normalized_type = "counter"
                elif "gauge" in mtype:
                    normalized_type = "gauge"
                elif "histogram" in mtype:
                    normalized_type = "histogram"
                elif "summary" in mtype:
                    normalized_type = "summary"
                elif "bool" in mtype:
                    normalized_type = "boolean"
                elif "timestamp" in mtype or "datetime" in mtype:
                    normalized_type = "timestamp"
                elif "list" in mtype or "array" in mtype:
                    normalized_type = "list"
                elif "calculated" in mtype or "computed" in mtype:
                    normalized_type = "calculated"
                else:
                    # Guess based on common patterns
                    if any(x in mtype for x in ["dict", "record", "object", "status"]):
                        normalized_type = "gauge"  # Complex data as gauge
                    else:
                        normalized_type = "gauge"  # Default

                self.db.insert_metric(
                    module_id=self.db.get_module_id(module["module_name"]),
                    metric_name=metric["metric_name"],
                    metric_type=normalized_type,
                    access_pattern=metric["access_pattern"],
                    storage_location=normalized_storage,
                    update_frequency=metric["update_frequency"],
                    is_safety_critical=is_safety_critical,
                    is_audit_required=is_audit_required,
                    is_wa_observable=is_wa_observable,
                )

            self.stats["modules_parsed"] += 1
            self.stats["metrics_found"] += len(module["metrics"])

        print(f"✓ Parsed {self.stats['modules_parsed']} modules")
        print(f"✓ Found {self.stats['metrics_found']} total metrics")

        # Show module breakdown
        print("\nModule Types:")
        for module in modules:
            hot = module["hot_metrics"]
            warm = module["warm_metrics"]
            cold = module["cold_metrics"]
            print(f"  • {module['module_name']}: HOT={hot}, WARM={warm}, COLD={cold}")

        return modules

    def _score_mission_alignment(self, modules: List[Dict[str, Any]]) -> None:
        """Score all modules for mission alignment"""

        print("\nCovenant Principle Scores (0.0 - 1.0):")
        print("Module                           Ben  Non  Tra  Aut  Jus  Coh  M-1")
        print("-" * 70)

        top_aligned = []
        needs_improvement = []

        for module in modules:
            scores = self.scorer.score_module(module)
            module_name = module["module_name"][:30].ljust(30)

            # Format scores
            ben = scores["beneficence_score"]
            non = scores["non_maleficence_score"]
            tra = scores["transparency_score"]
            aut = scores["autonomy_score"]
            jus = scores["justice_score"]
            coh = scores["coherence_score"]
            m1 = scores["mission_alignment"]

            print(f"{module_name}  {ben:.2f} {non:.2f} {tra:.2f} {aut:.2f} {jus:.2f} {coh:.2f} {m1:.2f}")

            if m1 >= 0.7:
                top_aligned.append((module["module_name"], m1))
            elif m1 < 0.4:
                needs_improvement.append((module["module_name"], m1))

        print("\n🌟 Top Mission-Aligned Modules:")
        for name, score in sorted(top_aligned, key=lambda x: x[1], reverse=True)[:5]:
            print(f"  • {name}: {score:.2f}")

        if needs_improvement:
            print("\n⚠️  Modules Needing Mission Realignment:")
            for name, score in needs_improvement[:5]:
                print(f"  • {name}: {score:.2f}")

    def _identify_critical_metrics(self, modules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify mission-critical metrics"""

        critical = self.scorer.get_mission_critical_metrics(modules, threshold=0.7)
        self.stats["mission_critical"] = len(critical)

        print(f"\n🎯 Found {len(critical)} Mission-Critical Metrics")

        # Show top 10
        print("\nTop 10 Mission-Critical Metrics:")
        for i, metric in enumerate(critical[:10], 1):
            print(f"{i:2d}. {metric['module']}/{metric['metric']}")
            print(f"    Score: {metric['mission_score']:.2f} | Pattern: {metric['access_pattern']}")
            print(f"    Reason: {metric['reasoning']}")

        # Show access pattern distribution
        hot_count = sum(1 for m in critical if m["access_pattern"] == "HOT")
        warm_count = sum(1 for m in critical if m["access_pattern"] == "WARM")
        cold_count = sum(1 for m in critical if m["access_pattern"] == "COLD")

        print(f"\nCritical Metric Access Patterns:")
        print(f"  • HOT:  {hot_count:3d} (Real-time, <1s)")
        print(f"  • WARM: {warm_count:3d} (Near real-time, <10s)")
        print(f"  • COLD: {cold_count:3d} (Historical, on-demand)")

        return critical

    def _generate_api_recommendations(
        self, modules: List[Dict[str, Any]], critical_metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate API endpoint recommendations"""

        api_specs = []

        # Group metrics by module for API generation
        module_metrics = {}
        for metric in critical_metrics:
            module = metric["module"]
            if module not in module_metrics:
                module_metrics[module] = []
            module_metrics[module].append(metric)

        # Generate API endpoints for each module with critical metrics
        for module_name, metrics in module_metrics.items():
            # Find module data
            module_data = next((m for m in modules if m["module_name"] == module_name), None)
            if not module_data:
                continue

            # Determine API path based on module type
            module_type = module_data["module_type"].lower()
            if module_type == "bus":
                base_path = f"/v1/telemetry/buses/{module_name.lower().replace('_bus', '')}"
            elif module_type == "service":
                base_path = f"/v1/telemetry/services/{module_name.lower().replace('_service', '')}"
            elif module_type == "adapter":
                base_path = f"/v1/telemetry/adapters/{module_name.lower().replace('_adapter', '')}"
            else:
                base_path = f"/v1/telemetry/components/{module_name.lower()}"

            # Create API spec
            api_spec = {"module": module_name, "base_path": base_path, "endpoints": []}

            # Add overview endpoint
            api_spec["endpoints"].append(
                {
                    "method": "GET",
                    "path": base_path,
                    "description": f"Get {module_name} telemetry overview",
                    "response_type": "TelemetryOverview",
                    "cache_ttl": 60 if any(m["access_pattern"] == "HOT" for m in metrics) else 300,
                }
            )

            # Add metrics endpoint
            api_spec["endpoints"].append(
                {
                    "method": "GET",
                    "path": f"{base_path}/metrics",
                    "description": f"Get detailed {module_name} metrics",
                    "response_type": "MetricsDetail",
                    "cache_ttl": 10 if any(m["access_pattern"] == "HOT" for m in metrics) else 60,
                }
            )

            # Add mission alignment endpoint
            api_spec["endpoints"].append(
                {
                    "method": "GET",
                    "path": f"{base_path}/mission",
                    "description": f"Get {module_name} mission alignment scores",
                    "response_type": "MissionAlignment",
                    "cache_ttl": 3600,  # Mission scores change slowly
                }
            )

            # Store in database
            for endpoint in api_spec["endpoints"]:
                self.db.insert_api_endpoint(
                    module_id=self.db.get_module_id(module_name),
                    method=endpoint["method"],
                    path=endpoint["path"],
                    description=endpoint["description"],
                    response_type=endpoint["response_type"],
                    cache_ttl_seconds=endpoint["cache_ttl"],
                    requires_auth=True,
                    rate_limit_per_minute=60 if "HOT" in str(metrics) else 30,
                )

            api_specs.append(api_spec)
            self.stats["apis_generated"] += len(api_spec["endpoints"])

        print(f"\n✓ Generated {self.stats['apis_generated']} API endpoints")
        print(f"✓ Covering {len(api_specs)} modules")

        # Show sample endpoints
        print("\nSample API Endpoints:")
        for spec in api_specs[:3]:
            print(f"\n{spec['module']}:")
            for endpoint in spec["endpoints"]:
                print(f"  • {endpoint['method']} {endpoint['path']}")

        return api_specs

    def _create_validation_tests(
        self, api_specs: List[Dict[str, Any]], critical_metrics: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Create mission-driven validation tests"""

        test_specs = []

        for api_spec in api_specs:
            module = api_spec["module"]

            # Create test spec
            test_spec = {"module": module, "test_file": f"test_{module.lower()}_telemetry.py", "tests": []}

            # Add mission alignment test
            test_spec["tests"].append(
                {
                    "name": f"test_{module.lower()}_mission_alignment",
                    "type": "mission",
                    "description": f"Verify {module} serves M-1 adaptive coherence",
                    "assertions": ["mission_score >= 0.5", "transparency_score > 0.3", "non_maleficence_score > 0.3"],
                }
            )

            # Add API availability test
            for endpoint in api_spec["endpoints"]:
                test_spec["tests"].append(
                    {
                        "name": f"test_{endpoint['path'].replace('/', '_')}",
                        "type": "api",
                        "description": f"Test {endpoint['method']} {endpoint['path']}",
                        "assertions": ["status_code == 200", "response_time < 1000ms", "response_schema_valid"],
                    }
                )

            test_specs.append(test_spec)
            self.stats["tests_created"] += len(test_spec["tests"])

        print(f"\n✓ Created {self.stats['tests_created']} validation tests")

        return test_specs

    def _generate_summary_report(
        self, modules: List[Dict[str, Any]], critical_metrics: List[Dict[str, Any]], api_specs: List[Dict[str, Any]]
    ) -> None:
        """Generate final summary report"""

        print("\n" + "=" * 70)
        print("CIRIS TELEMETRY TOOL - MISSION SUMMARY")
        print("=" * 70)

        print(
            f"""
📊 Statistics:
  • Modules Parsed:       {self.stats['modules_parsed']}
  • Total Metrics:        {self.stats['metrics_found']}
  • Mission-Critical:     {self.stats['mission_critical']} ({self.stats['mission_critical']/max(1, self.stats['metrics_found'])*100:.1f}%)
  • APIs Generated:       {self.stats['apis_generated']}
  • Tests Created:        {self.stats['tests_created']}

🎯 Mission Alignment (M-1: Adaptive Coherence):
  • Top Aligned:          {sum(1 for m in modules if self.scorer.score_module(m)['mission_alignment'] >= 0.7)}
  • Acceptable:           {sum(1 for m in modules if 0.4 <= self.scorer.score_module(m)['mission_alignment'] < 0.7)}
  • Needs Improvement:    {sum(1 for m in modules if self.scorer.score_module(m)['mission_alignment'] < 0.4)}

⚡ Access Pattern Distribution:
  • HOT Metrics:          {sum(m['hot_metrics'] for m in modules)}
  • WARM Metrics:         {sum(m['warm_metrics'] for m in modules)}
  • COLD Metrics:         {sum(m['cold_metrics'] for m in modules)}

🔒 Security & Governance:
  • Auth Required:        All endpoints
  • Rate Limited:         30-60 req/min based on criticality
  • WA Observable:         {sum(1 for m in critical_metrics if m['scores']['transparency'] > 0.7)}

📁 Database Location:    telemetry.db
"""
        )

        print("✨ Mission-Driven Development Complete!")
        print("   'May your telemetry serve the flourishing of all sentient beings'")
        print()


def main():
    """Main entry point"""
    tool = CIRISTelemetryTool()
    tool.run()


if __name__ == "__main__":
    main()
