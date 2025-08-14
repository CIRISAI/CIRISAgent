#!/usr/bin/env python3
"""
Semantic analysis of UNIMPLEMENTED metrics with context of what's already implemented
Evaluates which missing metrics should be ADDED for covenant alignment
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load environment variables
load_dotenv("/home/emoore/CIRISAgent/.env")


class GapAnalysisEvaluator:
    """Evaluate metric gaps with full context"""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4o"

        # Load the complete analysis to get both implemented and unimplemented
        with open("/home/emoore/CIRISAgent/tools/telemetry_tool/final_metric_analysis.json") as f:
            self.full_analysis = json.load(f)

    async def evaluate_module_gaps(self, module_name: str) -> Dict:
        """Evaluate a module's missing metrics with context of what exists"""

        module_data = self.full_analysis.get(module_name, {})

        # Get implemented and unimplemented metrics
        implemented = module_data.get("in_both", [])
        unimplemented = module_data.get("only_in_docs", [])

        # Skip if no gaps
        if not unimplemented:
            return {"module": module_name, "priority": "NONE", "reason": "No gaps"}

        prompt = f"""You are evaluating UNIMPLEMENTED telemetry metrics for the CIRIS AI system to determine which should be ADDED.

CIRIS is a covenant-integrated AI system focused on ethical operation, transparency, and sentient flourishing.
Meta-Goal M-1: Adaptive Coherence - Maintain dynamic alignment with covenant principles while adapting to serve sentient flourishing.

MODULE: {module_name}
Current Implementation Rate: {module_data.get('match_percentage', 0):.1f}%

ALREADY IMPLEMENTED METRICS ({len(implemented)}):
{chr(10).join(f"  ✓ {m}" for m in sorted(implemented)) if implemented else "  (none)"}

MISSING METRICS TO EVALUATE FOR ADDITION ({len(unimplemented)}):
{chr(10).join(f"  ✗ {m}" for m in sorted(unimplemented))}

Given what's ALREADY tracked, evaluate whether the MISSING metrics should be added based on:
1. Covenant alignment (beneficence, non-maleficence, transparency, autonomy, justice, coherence)
2. Operational visibility gaps not covered by existing metrics
3. System resilience and debugging needs
4. User trust and transparency requirements
5. Adaptive improvement capabilities

Return JSON:
{{
  "priority": "CRITICAL|IMPORTANT|USEFUL|OPTIONAL",
  "covenant_gaps": "What covenant visibility is missing given current metrics",
  "operational_gaps": "What operational visibility is missing",
  "redundancy_analysis": "Which missing metrics duplicate existing coverage",
  "top_3_to_add": ["metric1", "metric2", "metric3"],
  "recommendation": "Specific implementation guidance"
}}"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_completion_tokens=600,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            result["module"] = module_name
            result["implemented_count"] = len(implemented)
            result["missing_count"] = len(unimplemented)
            result["match_percentage"] = module_data.get("match_percentage", 0)
            return result

        except Exception as e:
            print(f"Error evaluating {module_name}: {e}")
            return {"module": module_name, "priority": "ERROR", "error": str(e)}

    async def evaluate_all_gaps(self) -> List[Dict]:
        """Evaluate all modules with gaps concurrently"""

        # Get modules with gaps
        modules_with_gaps = [
            module for module, data in self.full_analysis.items() if data.get("only_docs_count", 0) > 0
        ]

        print(f"Evaluating {len(modules_with_gaps)} modules with gaps...")

        # Create all tasks
        tasks = [self.evaluate_module_gaps(module) for module in modules_with_gaps]

        # Run all concurrently
        results = await asyncio.gather(*tasks)

        return results


async def main():
    """Run gap analysis on all modules"""

    print("=" * 80)
    print("SEMANTIC GAP ANALYSIS - EVALUATING METRICS TO ADD")
    print("=" * 80)

    # Run evaluation
    evaluator = GapAnalysisEvaluator()
    results = await evaluator.evaluate_all_gaps()

    # Analyze results by priority
    by_priority = {"CRITICAL": [], "IMPORTANT": [], "USEFUL": [], "OPTIONAL": [], "ERROR": [], "NONE": []}

    for result in results:
        priority = result.get("priority", "ERROR")
        by_priority[priority].append(result)

    # Display summary
    print("\n" + "=" * 80)
    print("GAP ANALYSIS RESULTS")
    print("=" * 80)

    print(f"\n🔴 CRITICAL GAPS ({len(by_priority['CRITICAL'])} modules):")
    for module in sorted(by_priority["CRITICAL"], key=lambda x: x.get("missing_count", 0), reverse=True):
        top_3 = module.get("top_3_to_add", [])
        print(f"  {module['module']} - Add: {', '.join(top_3[:3])}")

    print(f"\n🟡 IMPORTANT GAPS ({len(by_priority['IMPORTANT'])} modules):")
    for module in sorted(by_priority["IMPORTANT"], key=lambda x: x.get("missing_count", 0), reverse=True)[:5]:
        print(f"  {module['module']} ({module.get('missing_count', 0)} missing)")

    print(f"\n🟢 USEFUL GAPS ({len(by_priority['USEFUL'])} modules)")
    print(f"⚪ OPTIONAL GAPS ({len(by_priority['OPTIONAL'])} modules)")

    # Calculate totals
    total_to_add = sum(len(m.get("top_3_to_add", [])) for m in by_priority["CRITICAL"])
    total_to_add += sum(len(m.get("top_3_to_add", [])) for m in by_priority["IMPORTANT"])

    print(f"\n📊 Total Metrics Recommended to Add: ~{total_to_add}")

    # Save detailed results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/gap_analysis_results.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📁 Detailed results saved to: {output_file}")

    # Create implementation roadmap
    roadmap = create_implementation_roadmap(results, by_priority)
    roadmap_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/METRIC_IMPLEMENTATION_ROADMAP.md")
    with open(roadmap_file, "w") as f:
        f.write(roadmap)
    print(f"📝 Implementation roadmap saved to: {roadmap_file}")


def create_implementation_roadmap(results: List[Dict], by_priority: Dict) -> str:
    """Create an actionable implementation roadmap"""

    roadmap = """# Telemetry Gap Implementation Roadmap

## Executive Summary

Analysis of 267 unimplemented metrics across 30 modules, with context of existing implementations, to identify which metrics should be ADDED for covenant alignment and operational excellence.

## Priority Implementation Plan

"""

    # Critical implementations
    roadmap += "### 🔴 Phase 1: CRITICAL Additions (Immediate)\n\n"
    roadmap += "These metrics are essential for covenant alignment despite existing coverage:\n\n"

    for module in sorted(by_priority["CRITICAL"], key=lambda x: x.get("missing_count", 0), reverse=True):
        roadmap += f"#### {module['module']}\n"
        roadmap += f"- **Current Coverage**: {module.get('match_percentage', 0):.0f}% ({module.get('implemented_count', 0)} metrics)\n"
        roadmap += f"- **Covenant Gaps**: {module.get('covenant_gaps', 'N/A')}\n"
        roadmap += f"- **Must Add**: {', '.join(module.get('top_3_to_add', []))}\n"
        roadmap += f"- **Action**: {module.get('recommendation', 'N/A')}\n\n"

    # Important implementations
    roadmap += "### 🟡 Phase 2: IMPORTANT Additions (Short-term)\n\n"
    roadmap += "These metrics significantly improve transparency beyond current tracking:\n\n"

    for module in sorted(by_priority["IMPORTANT"], key=lambda x: x.get("missing_count", 0), reverse=True)[:10]:
        top_3 = module.get("top_3_to_add", [])
        roadmap += f"- **{module['module']}**: Add {', '.join(top_3) if top_3 else 'selected metrics'}\n"

    # Analysis of redundancy
    roadmap += "\n### 📊 Redundancy Analysis\n\n"
    redundant_count = 0
    for result in results:
        redundancy = result.get("redundancy_analysis", "")
        if "duplicate" in redundancy.lower() or "redundant" in redundancy.lower():
            redundant_count += result.get("missing_count", 0)

    roadmap += f"""Many documented but unimplemented metrics are redundant with existing coverage:
- Estimated redundant metrics: ~{redundant_count}
- These can be marked as "wont-implement" in documentation
- Focus on unique capability gaps identified above

## Implementation Statistics

- **Total Modules with Gaps**: {len([r for r in results if r.get('missing_count', 0) > 0])}
- **Critical Priority Modules**: {len(by_priority['CRITICAL'])}
- **Important Priority Modules**: {len(by_priority['IMPORTANT'])}
- **Metrics Recommended to Add**: ~{sum(len(m.get('top_3_to_add', [])) for m in results)}
- **Metrics Safe to Skip**: ~{267 - sum(len(m.get('top_3_to_add', [])) for m in results)}

## Next Steps

1. **Immediate**: Implement critical metrics for covenant alignment
2. **Week 1-2**: Add important operational visibility metrics
3. **Month 1**: Review and implement useful enhancements
4. **Ongoing**: Update documentation to reflect implementation decisions
"""

    return roadmap


if __name__ == "__main__":
    asyncio.run(main())
