#!/usr/bin/env python3
"""
Extract all UNIMPLEMENTED metrics for semantic analysis
Focus on the 48.5% gap to understand mission-critical missing telemetry
"""

import json
from pathlib import Path
from typing import Dict, List, Set


def extract_unimplemented_metrics():
    """Extract all metrics that are documented but not implemented"""

    # Load the final analysis results
    analysis_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/final_metric_analysis.json")
    with open(analysis_file) as f:
        results = json.load(f)

    unimplemented_metrics = []

    for module_name, module_data in results.items():
        # Skip if module has no documented metrics
        if module_data["documented_count"] == 0:
            continue

        # Get unimplemented metrics (in docs but not in code)
        for metric in module_data["only_in_docs"]:
            unimplemented_metrics.append(
                {
                    "module": module_name,
                    "metric": metric,
                    "module_category": categorize_module(module_name),
                    "implementation_status": "missing",
                    "match_percentage": module_data["match_percentage"],
                }
            )

    # Sort by module category and name
    unimplemented_metrics.sort(key=lambda x: (x["module_category"], x["module"], x["metric"]))

    return unimplemented_metrics


def categorize_module(module_name: str) -> str:
    """Categorize module for better organization"""
    if "_BUS" in module_name:
        return "Message_Bus"
    elif "_SERVICE" in module_name:
        if "TELEMETRY" in module_name or "AUDIT" in module_name or "CONFIG" in module_name:
            return "Graph_Service"
        elif "TIME" in module_name or "SHUTDOWN" in module_name or "INIT" in module_name:
            return "Infrastructure_Service"
        elif "WISE" in module_name or "FILTER" in module_name or "VISIBILITY" in module_name:
            return "Governance_Service"
        elif "LLM" in module_name or "RUNTIME" in module_name or "SCHEDULER" in module_name:
            return "Runtime_Service"
        else:
            return "Other_Service"
    elif "_COMPONENT" in module_name or "_PROCESSOR" in module_name or "_REGISTRY" in module_name:
        return "Component"
    elif "ADAPTER" in module_name:
        return "Adapter"
    else:
        return "Other"


def create_semantic_evaluation_prompt(metrics: List[Dict]) -> str:
    """Create prompt for semantic evaluation of unimplemented metrics"""

    # Group by module for better context
    by_module = {}
    for metric in metrics:
        module = metric["module"]
        if module not in by_module:
            by_module[module] = {
                "category": metric["module_category"],
                "match_rate": metric["match_percentage"],
                "missing_metrics": [],
            }
        by_module[module]["missing_metrics"].append(metric["metric"])

    prompt = """You are evaluating UNIMPLEMENTED telemetry metrics for the CIRIS AI system against Meta-Goal M-1 (Adaptive Coherence).

CIRIS is a covenant-integrated AI system focused on ethical operation, transparency, and sentient flourishing.

Meta-Goal M-1: Adaptive Coherence - The system should maintain dynamic alignment with its covenant principles while adapting to serve sentient flourishing.

For each module's MISSING metrics below, evaluate their importance for:
1. Covenant alignment (beneficence, non-maleficence, transparency, autonomy, justice, coherence)
2. Operational visibility and debugging
3. System health and resilience
4. User trust and transparency
5. Adaptive improvement capability

Rate each module's missing metrics as:
- CRITICAL: Essential for covenant alignment or system safety
- IMPORTANT: Significant for transparency or operational excellence
- USEFUL: Helpful but not essential
- OPTIONAL: Nice to have but minimal impact

UNIMPLEMENTED METRICS BY MODULE:\n\n"""

    for module_name, module_info in sorted(by_module.items()):
        prompt += f"## {module_name}\n"
        prompt += f"Category: {module_info['category']}\n"
        prompt += f"Current Implementation: {module_info['match_rate']:.1f}%\n"
        prompt += f"Missing Metrics:\n"
        for metric in module_info["missing_metrics"]:
            prompt += f"  - {metric}\n"
        prompt += "\n"

    prompt += """
Provide your evaluation in JSON format:
{
  "module_name": {
    "priority": "CRITICAL|IMPORTANT|USEFUL|OPTIONAL",
    "covenant_impact": "description of covenant alignment impact",
    "operational_impact": "description of operational impact",
    "key_missing_capabilities": ["list", "of", "critical", "gaps"],
    "recommendation": "specific action to take"
  }
}

Focus on identifying which missing metrics would most improve covenant alignment and system transparency."""

    return prompt, by_module


def main():
    """Extract unimplemented metrics and prepare for semantic analysis"""

    print("=" * 80)
    print("EXTRACTING UNIMPLEMENTED METRICS FOR SEMANTIC ANALYSIS")
    print("=" * 80)

    # Extract unimplemented metrics
    unimplemented = extract_unimplemented_metrics()

    # Statistics
    total_missing = len(unimplemented)
    by_category = {}
    for metric in unimplemented:
        cat = metric["module_category"]
        if cat not in by_category:
            by_category[cat] = 0
        by_category[cat] += 1

    print(f"\nTotal Unimplemented Metrics: {total_missing}")
    print("\nBy Category:")
    for cat, count in sorted(by_category.items()):
        print(f"  {cat:25} {count:3} metrics")

    # Save unimplemented metrics
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/unimplemented_metrics.json")
    with open(output_file, "w") as f:
        json.dump(unimplemented, f, indent=2)
    print(f"\n📁 Unimplemented metrics saved to: {output_file}")

    # Create semantic evaluation prompt
    prompt, by_module = create_semantic_evaluation_prompt(unimplemented)

    # Save prompt for semantic evaluation
    prompt_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/unimplemented_evaluation_prompt.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)
    print(f"📝 Evaluation prompt saved to: {prompt_file}")

    # Show summary of modules with most missing metrics
    print("\n🔴 Modules with Most Missing Metrics:")
    module_counts = {}
    for metric in unimplemented:
        if metric["module"] not in module_counts:
            module_counts[metric["module"]] = 0
        module_counts[metric["module"]] += 1

    for module, count in sorted(module_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {module:35} {count:3} missing metrics")

    return unimplemented, by_module


if __name__ == "__main__":
    main()
