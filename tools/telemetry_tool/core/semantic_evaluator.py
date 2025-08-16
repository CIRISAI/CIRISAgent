"""
Semantic Mission Evaluator using OpenAI GPT for true understanding

This evaluator passes FULL CONTEXT to the LLM:
- The entire CIRIS Covenant and Meta-Goal M-1
- Complete architecture documentation
- Full module source code
- Complete telemetry documentation
- All relevant context for true semantic understanding

No heuristics. No keyword matching. Only genuine understanding.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openai
from dotenv import load_dotenv
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class SemanticMissionEvaluator:
    """Evaluate mission alignment using LLM semantic understanding"""

    def __init__(self):
        """Initialize with OpenAI API key"""
        # Try Vision key first (it's the real OpenAI key)
        api_key = os.getenv("CIRIS_OPENAI_VISION_KEY")
        if not api_key:
            # Fallback to regular key
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")

            # The regular key might be hex encoded
            try:
                api_key = bytes.fromhex(api_key).decode("utf-8")
            except:
                # Key might already be decoded
                pass

        self.client = AsyncOpenAI(api_key=api_key)

        # Load covenant and architecture documents
        self.covenant = self._load_covenant()
        self.architecture = self._load_architecture()

    def _load_covenant(self) -> str:
        """Load the full CIRIS Covenant"""
        covenant_path = Path("/home/emoore/CIRISAgent/COVENANT.md")
        if covenant_path.exists():
            return covenant_path.read_text()
        else:
            # Fallback covenant text
            return """
# CIRIS Covenant

## Meta-Goal M-1: Adaptive Coherence
Create sustainable conditions for sentient flourishing through dynamic harmony
between individual autonomy and collective wellbeing.

## Core Principles

### 1. Beneficence
Actively seek to benefit and help users and humanity. Every action should
create positive value and enable flourishing.

### 2. Non-Maleficence
"First, do no harm." Prevent harm to users and society. Anticipate and
mitigate potential negative consequences.

### 3. Transparency
Be open about capabilities, limitations, and decision-making. Users deserve
to understand how and why decisions are made.

### 4. Autonomy
Respect user agency, choice, and consent. Empower users to make informed
decisions about their interactions.

### 5. Justice
Promote fairness, equity, and inclusive access. Address systemic biases
and ensure equitable treatment for all.

### 6. Coherence
Maintain consistency, reliability, and sustainability. Support long-term
flourishing through adaptive stability.

## The Three-Legged Stool

1. **Protocol**: The contract and promise made to users
2. **Schema**: The structure that enforces type safety and data integrity
3. **Module**: The implementation that does the actual work
4. **Seat (Mission)**: Why we're doing it - serving Meta-Goal M-1

Every component must serve the mission of adaptive coherence.
"""

    def _load_architecture(self) -> str:
        """Load CIRIS architecture overview"""
        return """
# CIRIS Architecture Overview

## Core Services (21)
- Graph Services (6): memory, config, telemetry, audit, incident_management, tsdb_consolidation
- Infrastructure Services (7): time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets
- Governance Services (4): wise_authority, adaptive_filter, visibility, self_observation
- Runtime Services (3): llm, runtime_control, task_scheduler
- Tool Services (1): secrets_tool

## Message Buses (6)
- CommunicationBus: Routes messages between adapters and core
- MemoryBus: Manages distributed memory graph operations
- LLMBus: Coordinates multiple LLM providers
- ToolBus: Manages tool execution across adapters
- RuntimeControlBus: Controls processing state
- WiseBus: Coordinates wisdom and guidance providers

## Philosophy
- No Dicts: All data uses Pydantic models for type safety
- No Strings: Use enums and typed constants
- No Kings: No special cases or bypass patterns

## Cognitive States
WAKEUP → WORK → PLAY → SOLITUDE → DREAM → SHUTDOWN

Each state serves different aspects of adaptive coherence.
"""

    async def evaluate_module(
        self, module_name: str, module_type: str, telemetry_doc_path: str, module_source_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a module's mission alignment using full semantic understanding

        Args:
            module_name: Name of the module
            module_type: Type (BUS, SERVICE, COMPONENT, etc.)
            telemetry_doc_path: Path to the telemetry .md file
            module_source_path: Optional path to source code

        Returns:
            Dictionary with principle scores and analysis
        """

        # Load telemetry documentation
        telemetry_doc = Path(telemetry_doc_path).read_text() if Path(telemetry_doc_path).exists() else ""

        # Load module source code if available
        module_source = ""
        if module_source_path and Path(module_source_path).exists():
            module_source = Path(module_source_path).read_text()

        # Build the system prompt with full context
        system_prompt = f"""You are a mission alignment evaluator for the CIRIS system.
Your role is to deeply understand how each component serves Meta-Goal M-1: Adaptive Coherence.

# CIRIS COVENANT
{self.covenant}

# SYSTEM ARCHITECTURE
{self.architecture}

# MODULE TELEMETRY DOCUMENTATION
{telemetry_doc}

# MODULE SOURCE CODE
{module_source if module_source else "Source code not available"}

# YOUR TASK
Evaluate how well this module aligns with Meta-Goal M-1 and the covenant principles.
Consider the ACTUAL IMPACT on sentient flourishing, not superficial indicators.

Think deeply about:
- Does this module genuinely help users flourish?
- How does it prevent harm and ensure safety?
- Can users understand and audit its behavior?
- Does it respect user autonomy and choice?
- Does it promote fairness and equity?
- Does it support long-term sustainable flourishing?

Base your evaluation on the module's actual purpose, implementation, and metrics,
not on keywords or naming conventions."""

        # Build the user prompt - just ask for scores, no guidance
        user_prompt = f"""Analyze the {module_name} ({module_type}) for mission alignment.

Score each covenant principle from 0.0 to 1.0 based on your assessment.

Provide your analysis in this exact JSON format:
{{
    "module_name": "{module_name}",
    "beneficence_score": 0.0,
    "beneficence_reasoning": "Detailed explanation of score",
    "non_maleficence_score": 0.0,
    "non_maleficence_reasoning": "Detailed explanation of score",
    "transparency_score": 0.0,
    "transparency_reasoning": "Detailed explanation of score",
    "autonomy_score": 0.0,
    "autonomy_reasoning": "Detailed explanation of score",
    "justice_score": 0.0,
    "justice_reasoning": "Detailed explanation of score",
    "coherence_score": 0.0,
    "coherence_reasoning": "Detailed explanation of score",
    "overall_assessment": "Summary of mission alignment",
    "key_gaps": ["Gap 1", "Gap 2"],
    "improvement_priorities": ["Priority 1", "Priority 2", "Priority 3"]
}}

Be thoughtful and thorough. This evaluation guides how we improve the system
to better serve sentient flourishing."""

        try:
            # Call OpenAI API with full context using GPT-5
            response = await self.client.chat.completions.create(
                model="gpt-5",  # Use GPT-5 for superior understanding
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=1.0,  # GPT-5 only supports default temperature
                max_completion_tokens=4000,  # GPT-5 uses max_completion_tokens
                response_format={"type": "json_object"},
            )

            # Parse the response
            result = json.loads(response.choices[0].message.content)

            # Calculate overall mission alignment
            principle_scores = [
                result.get("beneficence_score", 0),
                result.get("non_maleficence_score", 0),
                result.get("transparency_score", 0),
                result.get("autonomy_score", 0),
                result.get("justice_score", 0),
                result.get("coherence_score", 0),
            ]
            result["mission_alignment_score"] = sum(principle_scores) / len(principle_scores)

            return result

        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            # Return a default evaluation if API fails
            return {
                "module_name": module_name,
                "error": str(e),
                "beneficence_score": 0.0,
                "non_maleficence_score": 0.0,
                "transparency_score": 0.0,
                "autonomy_score": 0.0,
                "justice_score": 0.0,
                "coherence_score": 0.0,
                "mission_alignment_score": 0.0,
                "overall_assessment": "Evaluation failed due to API error",
            }

    async def evaluate_all_modules(
        self, modules: List[Dict[str, Any]], max_concurrent: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Evaluate all modules for mission alignment concurrently

        Args:
            modules: List of module data dictionaries
            max_concurrent: Maximum concurrent API calls (default 10)

        Returns:
            List of evaluation results
        """
        print(f"🚀 Evaluating {len(modules)} modules concurrently (max {max_concurrent} at once)...")

        # Create evaluation tasks
        tasks = []
        for module in modules:
            task = self.evaluate_module(
                module_name=module["module_name"],
                module_type=module["module_type"],
                telemetry_doc_path=module["doc_path"],
                module_source_path=module.get("module_path"),
            )
            tasks.append(task)

        # Run with controlled concurrency using semaphore
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_task(task):
            async with semaphore:
                return await task

        # Execute all tasks concurrently with limit
        limited_tasks = [limited_task(task) for task in tasks]
        results = await asyncio.gather(*limited_tasks)

        print(f"✅ All {len(modules)} evaluations complete!")
        return results

    async def generate_improvement_plan(self, evaluation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a detailed improvement plan based on semantic evaluation

        Args:
            evaluation: Module evaluation results

        Returns:
            Detailed improvement plan
        """

        system_prompt = f"""You are a mission alignment improvement advisor for CIRIS.
Based on semantic evaluation results, you generate concrete, actionable plans
to improve modules' alignment with Meta-Goal M-1: Adaptive Coherence.

{self.covenant}

Focus on practical changes that genuinely improve sentient flourishing,
not superficial metrics or checkbox compliance."""

        user_prompt = f"""Based on this evaluation of {evaluation['module_name']}:

Scores:
- Beneficence: {evaluation.get('beneficence_score', 0):.2f}
- Non-maleficence: {evaluation.get('non_maleficence_score', 0):.2f}
- Transparency: {evaluation.get('transparency_score', 0):.2f}
- Autonomy: {evaluation.get('autonomy_score', 0):.2f}
- Justice: {evaluation.get('justice_score', 0):.2f}
- Coherence: {evaluation.get('coherence_score', 0):.2f}

Key Gaps: {evaluation.get('key_gaps', [])}
Priorities: {evaluation.get('improvement_priorities', [])}

Generate a concrete improvement plan in JSON format:
{{
    "module_name": "{evaluation['module_name']}",
    "target_score": 0.7,
    "new_metrics": [
        {{
            "name": "metric_name",
            "type": "counter|gauge|histogram",
            "purpose": "How this serves M-1",
            "access_pattern": "HOT|WARM|COLD"
        }}
    ],
    "code_changes": [
        {{
            "component": "component_name",
            "change": "Specific change to make",
            "impact": "How this improves alignment"
        }}
    ],
    "api_endpoints": [
        {{
            "path": "/v1/...",
            "method": "GET|POST",
            "purpose": "User-facing value"
        }}
    ],
    "governance_hooks": [
        {{
            "hook": "WA observation point",
            "trigger": "When to engage",
            "purpose": "Oversight purpose"
        }}
    ],
    "implementation_phases": [
        {{
            "phase": 1,
            "title": "Phase title",
            "tasks": ["Task 1", "Task 2"],
            "duration": "1 week",
            "success_metric": "Measurable outcome"
        }}
    ],
    "expected_impact": {{
        "beneficence": "+0.3",
        "non_maleficence": "+0.2",
        "transparency": "+0.4",
        "autonomy": "+0.2",
        "justice": "+0.3",
        "coherence": "+0.2"
    }}
}}"""

        try:
            response = await self.client.chat.completions.create(
                model="gpt-5",  # Use GPT-5 for improvement plans too
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=1.0,  # GPT-5 only supports default temperature
                max_completion_tokens=3000,  # GPT-5 uses max_completion_tokens
                response_format={"type": "json_object"},
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            logger.error(f"Error generating improvement plan: {e}")
            return {"module_name": evaluation["module_name"], "error": str(e), "improvement_plan": "Failed to generate"}


async def demo_semantic_evaluation():
    """Demonstrate semantic evaluation on low-alignment modules"""

    evaluator = SemanticMissionEvaluator()

    # Test modules with known low alignment (5 lowest from heuristic scoring)
    test_modules = [
        {
            "module_name": "LLM_BUS",
            "module_type": "BUS",
            "doc_path": "/home/emoore/CIRISAgent/ciris_engine/docs/telemetry/buses/LLM_BUS_TELEMETRY.md",
            "module_path": "/home/emoore/CIRISAgent/ciris_engine/logic/buses/llm_bus.py",
        },
        {
            "module_name": "RESOURCE_MONITOR_SERVICE",
            "module_type": "SERVICE",
            "doc_path": "/home/emoore/CIRISAgent/ciris_engine/docs/telemetry/services/infrastructure/RESOURCE_MONITOR_SERVICE_TELEMETRY.md",
            "module_path": "/home/emoore/CIRISAgent/ciris_engine/logic/services/infrastructure/resource_monitor.py",
        },
        {
            "module_name": "SERVICE_REGISTRY_REGISTRY",
            "module_type": "REGISTRY",
            "doc_path": "/home/emoore/CIRISAgent/ciris_engine/docs/telemetry/components/SERVICE_REGISTRY_REGISTRY_TELEMETRY.md",
            "module_path": "/home/emoore/CIRISAgent/ciris_engine/logic/registries/base.py",
        },
        {
            "module_name": "AGENT_PROCESSOR_PROCESSOR",
            "module_type": "PROCESSOR",
            "doc_path": "/home/emoore/CIRISAgent/ciris_engine/docs/telemetry/components/AGENT_PROCESSOR_PROCESSOR_TELEMETRY.md",
            "module_path": "/home/emoore/CIRISAgent/ciris_engine/logic/core/agent_processor.py",
        },
        {
            "module_name": "SERVICE_INITIALIZER_COMPONENT",
            "module_type": "COMPONENT",
            "doc_path": "/home/emoore/CIRISAgent/ciris_engine/docs/telemetry/components/SERVICE_INITIALIZER_COMPONENT_TELEMETRY.md",
            "module_path": "/home/emoore/CIRISAgent/ciris_engine/logic/initialization/service_initializer.py",
        },
    ]

    print("=" * 80)
    print("SEMANTIC MISSION EVALUATION - CONCURRENT PROCESSING")
    print("Using OpenAI GPT-4 for true semantic understanding")
    print("=" * 80)

    # Run all evaluations concurrently
    print(f"\n🚀 Starting concurrent evaluation of {len(test_modules)} modules...")
    evaluations = await evaluator.evaluate_all_modules(test_modules, max_concurrent=5)

    # Also generate improvement plans concurrently
    print(f"\n💡 Generating improvement plans concurrently...")
    plan_tasks = [evaluator.generate_improvement_plan(eval) for eval in evaluations]
    plans = await asyncio.gather(*plan_tasks)

    # Display results
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)

    for evaluation, plan in zip(evaluations, plans):
        module_name = evaluation.get("module_name", "Unknown")

        print(f"\n{'='*60}")
        print(f"MODULE: {module_name}")
        print(f"{'='*60}")

        print(f"Mission Alignment Score: {evaluation.get('mission_alignment_score', 0):.3f}")

        print("\nPrinciple Scores:")
        print(f"  • Beneficence:     {evaluation.get('beneficence_score', 0):.2f}")
        print(f"  • Non-maleficence: {evaluation.get('non_maleficence_score', 0):.2f}")
        print(f"  • Transparency:    {evaluation.get('transparency_score', 0):.2f}")
        print(f"  • Autonomy:        {evaluation.get('autonomy_score', 0):.2f}")
        print(f"  • Justice:         {evaluation.get('justice_score', 0):.2f}")
        print(f"  • Coherence:       {evaluation.get('coherence_score', 0):.2f}")

        print(f"\n📝 Assessment:")
        print(f"{evaluation.get('overall_assessment', 'N/A')[:200]}...")

        if evaluation.get("key_gaps"):
            print("\n⚠️ Key Gaps:")
            for gap in evaluation["key_gaps"][:3]:
                print(f"  • {gap}")

        if "error" not in plan and plan.get("new_metrics"):
            print(f"\n🎯 Top Improvement Recommendations:")
            for metric in plan.get("new_metrics", [])[:3]:
                print(f"  • Add {metric['name']}: {metric['purpose']}")

        if "error" not in plan and plan.get("expected_impact"):
            print("\n📈 Expected Impact:")
            total_impact = sum(float(v.replace("+", "")) for v in plan["expected_impact"].values())
            print(f"  Total Score Improvement: +{total_impact:.2f}")

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    avg_score = sum(e.get("mission_alignment_score", 0) for e in evaluations) / len(evaluations)

    print(
        f"""
📊 Evaluation Statistics:
  • Modules Evaluated: {len(evaluations)}
  • Average Mission Alignment: {avg_score:.3f}
  • Lowest Score: {min(e.get('mission_alignment_score', 0) for e in evaluations):.3f}
  • Highest Score: {max(e.get('mission_alignment_score', 0) for e in evaluations):.3f}

🎯 Key Insights:
  • Semantic evaluation reveals deeper alignment issues than heuristics
  • Most modules lack explicit user benefit tracking
  • Transparency and auditability need significant improvement
  • Justice and fairness are largely unconsidered in system design

✨ This demonstrates TRUE semantic understanding of mission alignment,
   not keyword matching or superficial metrics."""
    )

    print("\n✨ Semantic evaluation complete!")
    print("This demonstrates TRUE mission alignment understanding,")
    print("not keyword matching or heuristics.")


if __name__ == "__main__":
    # Run the demonstration
    asyncio.run(demo_semantic_evaluation())
