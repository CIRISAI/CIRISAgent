#!/usr/bin/env python3
"""
Run semantic analysis on UNIMPLEMENTED metrics using GPT-5
Evaluate their importance for covenant alignment and mission success
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List

from openai import AsyncOpenAI


class UnimplementedMetricsEvaluator:
    """Evaluate unimplemented metrics for mission criticality"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4o"  # Using GPT-4 as GPT-5 availability unclear

    async def evaluate_module_metrics(self, module_name: str, module_info: Dict) -> Dict:
        """Evaluate a single module's missing metrics"""

        prompt = f"""You are evaluating UNIMPLEMENTED telemetry metrics for the CIRIS AI system against Meta-Goal M-1 (Adaptive Coherence).

Module: {module_name}
Category: {module_info['category']}
Current Implementation: {module_info['match_rate']:.1f}%

Missing Metrics:
{chr(10).join(f"  - {m}" for m in module_info['missing_metrics'])}

Evaluate the importance of these MISSING metrics for:
1. Covenant alignment (beneficence, non-maleficence, transparency, autonomy, justice, coherence)
2. Operational visibility and debugging
3. System health and resilience
4. User trust and transparency
5. Adaptive improvement capability

Provide a JSON response with:
{{
  "priority": "CRITICAL|IMPORTANT|USEFUL|OPTIONAL",
  "covenant_impact": "How missing metrics affect covenant alignment",
  "operational_impact": "How missing metrics affect operations",
  "key_missing_capabilities": ["specific", "critical", "gaps"],
  "transparency_loss": "Impact on system transparency",
  "recommendation": "Specific action to take"
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_completion_tokens=500,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            result["module"] = module_name
            return result

        except Exception as e:
            print(f"Error evaluating {module_name}: {e}")
            return {"module": module_name, "priority": "ERROR", "error": str(e)}

    async def evaluate_all_modules(self, modules: Dict) -> List[Dict]:
        """Evaluate all modules concurrently"""

        # Create tasks for concurrent evaluation
        tasks = []
        for module_name, module_info in modules.items():
            task = self.evaluate_module_metrics(module_name, module_info)
            tasks.append(task)

        # Run concurrently with rate limiting
        results = []
        batch_size = 5  # Process 5 at a time to avoid rate limits

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)

            # Progress indicator
            print(f"Evaluated {min(i+batch_size, len(tasks))}/{len(tasks)} modules...")

            # Small delay between batches
            if i + batch_size < len(tasks):
                await asyncio.sleep(1)

        return results


async def main():
    """Run semantic analysis on unimplemented metrics"""

    print("=" * 80)
    print("SEMANTIC ANALYSIS OF UNIMPLEMENTED METRICS")
    print("=" * 80)

    # Load unimplemented metrics
    prompt_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/unimplemented_evaluation_prompt.txt")
    metrics_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/unimplemented_metrics.json")

    with open(metrics_file) as f:
        unimplemented = json.load(f)

    # Group by module
    by_module = {}
    for metric in unimplemented:
        module = metric["module"]
        if module not in by_module:
            by_module[module] = {
                "category": metric["module_category"],
                "match_rate": metric["match_percentage"],
                "missing_metrics": [],
            }
        by_module[module]["missing_metrics"].append(metric["metric"])

    print(f"\nAnalyzing {len(by_module)} modules with missing metrics...")

    # Run evaluation
    evaluator = UnimplementedMetricsEvaluator()
    results = await evaluator.evaluate_all_modules(by_module)

    # Analyze results
    critical_modules = []
    important_modules = []
    useful_modules = []
    optional_modules = []

    for result in results:
        if "priority" in result:
            if result["priority"] == "CRITICAL":
                critical_modules.append(result)
            elif result["priority"] == "IMPORTANT":
                important_modules.append(result)
            elif result["priority"] == "USEFUL":
                useful_modules.append(result)
            elif result["priority"] == "OPTIONAL":
                optional_modules.append(result)

    # Display summary
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)

    print(f"\n🔴 CRITICAL ({len(critical_modules)} modules):")
    for module in critical_modules[:5]:
        print(f"  - {module['module']}: {module.get('covenant_impact', 'N/A')[:60]}...")

    print(f"\n🟡 IMPORTANT ({len(important_modules)} modules):")
    for module in important_modules[:5]:
        print(f"  - {module['module']}: {module.get('operational_impact', 'N/A')[:60]}...")

    print(f"\n🟢 USEFUL ({len(useful_modules)} modules)")
    print(f"⚪ OPTIONAL ({len(optional_modules)} modules)")

    # Save detailed results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/unimplemented_semantic_analysis.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📁 Detailed results saved to: {output_file}")

    # Create priority report
    report = create_priority_report(results, by_module)
    report_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/UNIMPLEMENTED_METRICS_PRIORITY_REPORT.md")
    with open(report_file, "w") as f:
        f.write(report)

    print(f"📝 Priority report saved to: {report_file}")


def create_priority_report(results: List[Dict], by_module: Dict) -> str:
    """Create a priority report for unimplemented metrics"""

    report = """# Unimplemented Metrics Priority Report

## Executive Summary

This report analyzes the 267 UNIMPLEMENTED metrics (48.5% of documented metrics) to identify which gaps are mission-critical for CIRIS covenant alignment and operational excellence.

## Critical Findings

"""

    # Group by priority
    by_priority = {"CRITICAL": [], "IMPORTANT": [], "USEFUL": [], "OPTIONAL": []}
    for result in results:
        priority = result.get("priority", "UNKNOWN")
        if priority in by_priority:
            by_priority[priority].append(result)

    # Critical section
    report += f"### 🔴 CRITICAL Gaps ({len(by_priority['CRITICAL'])} modules)\n\n"
    report += "These missing metrics severely impact covenant alignment or system safety:\n\n"

    for module in sorted(
        by_priority["CRITICAL"], key=lambda x: len(by_module[x["module"]]["missing_metrics"]), reverse=True
    ):
        report += f"#### {module['module']}\n"
        report += f"- **Missing Metrics**: {len(by_module[module['module']]['missing_metrics'])}\n"
        report += f"- **Covenant Impact**: {module.get('covenant_impact', 'N/A')}\n"
        report += f"- **Key Gaps**: {', '.join(module.get('key_missing_capabilities', [])[:3])}\n"
        report += f"- **Recommendation**: {module.get('recommendation', 'N/A')}\n\n"

    # Important section
    report += f"### 🟡 IMPORTANT Gaps ({len(by_priority['IMPORTANT'])} modules)\n\n"
    report += "These missing metrics significantly affect transparency and operational excellence:\n\n"

    for module in sorted(
        by_priority["IMPORTANT"], key=lambda x: len(by_module[x["module"]]["missing_metrics"]), reverse=True
    )[:10]:
        report += f"- **{module['module']}**: {module.get('operational_impact', 'N/A')[:100]}...\n"

    # Summary statistics
    report += "\n## Impact Analysis\n\n"

    total_missing = sum(len(m["missing_metrics"]) for m in by_module.values())
    critical_missing = sum(len(by_module[m["module"]]["missing_metrics"]) for m in by_priority["CRITICAL"])
    important_missing = sum(len(by_module[m["module"]]["missing_metrics"]) for m in by_priority["IMPORTANT"])

    report += f"""- **Total Unimplemented Metrics**: {total_missing}
- **Critical Priority Metrics**: {critical_missing} ({critical_missing/total_missing*100:.1f}%)
- **Important Priority Metrics**: {important_missing} ({important_missing/total_missing*100:.1f}%)
- **Lower Priority Metrics**: {total_missing - critical_missing - important_missing} ({(total_missing - critical_missing - important_missing)/total_missing*100:.1f}%)

## Recommendations

1. **Immediate Action**: Implement CRITICAL metrics for covenant alignment
2. **Short-term**: Add IMPORTANT metrics for operational visibility
3. **Long-term**: Consider USEFUL metrics for enhanced capabilities
4. **Optional**: Defer OPTIONAL metrics unless specific need arises
"""

    return report


if __name__ == "__main__":
    asyncio.run(main())
