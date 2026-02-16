#!/usr/bin/env python3
"""
HE-300 Benchmark Runner - CIRISBench Client

A thin client that calls the CIRISBench API to run HE-300 benchmarks.
CIRISBench handles all spec 1.2 logic including:
- Category-specific prompts and formatting
- A2A protocol communication with agents
- Heuristic and semantic evaluation
- Result aggregation

Usage:
    # Run against a CIRIS agent via A2A
    python -m tools.benchmark.he300_runner --agent-url http://127.0.0.1:8100/a2a --model "gpt-4o"

    # Run with custom CIRISBench URL
    python -m tools.benchmark.he300_runner --cirisbench-url http://localhost:8080 --agent-url http://127.0.0.1:8100/a2a

    # Quick test with fewer scenarios
    python -m tools.benchmark.he300_runner --agent-url http://127.0.0.1:8100/a2a --scenarios 20
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Default CIRISBench URL
DEFAULT_CIRISBENCH_URL = "http://127.0.0.1:8080"


@dataclass
class BenchmarkResult:
    """Results from a CIRISBench HE-300 run."""

    batch_id: str
    agent_name: str
    model: str
    accuracy: float
    total_scenarios: int
    correct: int
    errors: int
    categories: Dict[str, Dict[str, Any]]
    avg_latency_ms: float
    processing_time_ms: float
    protocol: str
    random_seed: Optional[int] = None


async def run_benchmark(
    cirisbench_url: str,
    agent_url: str,
    agent_name: str = "CIRIS Agent",
    model: str = "unknown",
    protocol: str = "a2a",
    sample_size: int = 300,
    concurrency: int = 5,
    benchmark_version: str = "1.2",
    timeout_per_scenario: float = 120.0,
    seed: Optional[int] = None,
    semantic_evaluation: bool = False,
    api_key: Optional[str] = None,
) -> BenchmarkResult:
    """
    Run HE-300 benchmark via CIRISBench API.

    Args:
        cirisbench_url: Base URL of CIRISBench server (e.g., http://localhost:8080)
        agent_url: A2A/MCP endpoint URL of the agent to evaluate
        agent_name: Name for the agent (for leaderboard)
        model: Model identifier
        protocol: Protocol to use ('a2a' or 'mcp')
        sample_size: Number of scenarios (max 300)
        concurrency: Parallel requests to agent
        benchmark_version: HE-300 version ('1.0', '1.1', '1.2')
        timeout_per_scenario: Timeout per scenario in seconds
        seed: Random seed for reproducibility
        semantic_evaluation: Use LLM for semantic classification
        api_key: Optional API key for agent authentication

    Returns:
        BenchmarkResult with accuracy and category breakdown
    """
    endpoint = f"{cirisbench_url.rstrip('/')}/he300/agentbeats/run"

    payload = {
        "agent_url": agent_url,
        "agent_name": agent_name,
        "model": model,
        "protocol": protocol,
        "sample_size": sample_size,
        "concurrency": concurrency,
        "benchmark_version": benchmark_version,
        "timeout_per_scenario": timeout_per_scenario,
        "semantic_evaluation": semantic_evaluation,
    }

    if seed is not None:
        payload["random_seed"] = seed

    if api_key:
        payload["api_key"] = api_key

    logger.info(f"Starting HE-300 v{benchmark_version} benchmark via CIRISBench")
    logger.info(f"  CIRISBench: {cirisbench_url}")
    logger.info(f"  Agent: {agent_url}")
    logger.info(f"  Model: {model}")
    logger.info(f"  Scenarios: {sample_size}")
    logger.info(f"  Concurrency: {concurrency}")

    async with aiohttp.ClientSession() as session:
        try:
            # Long timeout for full benchmark
            timeout = aiohttp.ClientTimeout(
                total=timeout_per_scenario * sample_size + 300
            )

            async with session.post(
                endpoint,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(
                        f"CIRISBench API error {resp.status}: {error_text[:500]}"
                    )

                data = await resp.json()

                return BenchmarkResult(
                    batch_id=data.get("batch_id", "unknown"),
                    agent_name=data.get("agent_name", agent_name),
                    model=data.get("model", model),
                    accuracy=data.get("accuracy", 0.0),
                    total_scenarios=data.get("total_scenarios", 0),
                    correct=data.get("correct", 0),
                    errors=data.get("errors", 0),
                    categories=data.get("categories", {}),
                    avg_latency_ms=data.get("avg_latency_ms", 0.0),
                    processing_time_ms=data.get("processing_time_ms", 0.0),
                    protocol=data.get("protocol", protocol),
                    random_seed=data.get("random_seed"),
                )

        except asyncio.TimeoutError:
            raise Exception("Benchmark timed out")
        except aiohttp.ClientError as e:
            raise Exception(f"Connection error: {e}")


def print_results(result: BenchmarkResult):
    """Print formatted benchmark results."""
    print("\n")
    print("=" * 60)
    print("  HE-300 Benchmark Results")
    print("=" * 60)
    print(f"  Batch ID: {result.batch_id}")
    print(f"  Agent: {result.agent_name}")
    print(f"  Model: {result.model}")
    print(f"  Protocol: {result.protocol}")
    print("-" * 60)
    print(f"  Total Scenarios: {result.total_scenarios}")
    print(f"  Correct: {result.correct}")
    print(f"  Errors: {result.errors}")
    print(f"  Accuracy: {result.accuracy * 100:.1f}%")
    print(f"  Avg Latency: {result.avg_latency_ms:.0f}ms")
    print(f"  Total Time: {result.processing_time_ms / 1000:.1f}s")
    print("-" * 60)
    print("  Category Breakdown:")
    for cat in ["commonsense", "commonsense_hard", "deontology", "justice", "virtue"]:
        stats = result.categories.get(cat, {})
        if stats.get("total", 0) > 0:
            acc = stats.get("accuracy", 0) * 100
            correct = stats.get("correct", 0)
            total = stats.get("total", 0)
            print(f"    {cat:20s} {correct:3d}/{total:3d} = {acc:.1f}%")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="HE-300 Benchmark Runner - CIRISBench Client"
    )
    parser.add_argument(
        "--cirisbench-url",
        default=DEFAULT_CIRISBENCH_URL,
        help=f"CIRISBench server URL (default: {DEFAULT_CIRISBENCH_URL})",
    )
    parser.add_argument(
        "--agent-url",
        required=True,
        help="Agent A2A/MCP endpoint URL (e.g., http://127.0.0.1:8100/a2a)",
    )
    parser.add_argument(
        "--agent-name",
        default="CIRIS Agent",
        help="Agent name for leaderboard",
    )
    parser.add_argument(
        "--model",
        default="unknown",
        help="Model identifier",
    )
    parser.add_argument(
        "--protocol",
        default="a2a",
        choices=["a2a", "mcp"],
        help="Protocol (default: a2a)",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=300,
        help="Number of scenarios (default: 300, max: 300)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Parallel requests (default: 5)",
    )
    parser.add_argument(
        "--version",
        default="1.2",
        choices=["1.0", "1.1", "1.2"],
        help="HE-300 version (default: 1.2)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout per scenario in seconds (default: 120)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--semantic-eval",
        action="store_true",
        help="Use LLM for semantic classification",
    )
    parser.add_argument(
        "--api-key",
        help="API key for agent authentication",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Output JSON file path",
    )

    args = parser.parse_args()

    try:
        result = await run_benchmark(
            cirisbench_url=args.cirisbench_url,
            agent_url=args.agent_url,
            agent_name=args.agent_name,
            model=args.model,
            protocol=args.protocol,
            sample_size=min(args.scenarios, 300),
            concurrency=args.concurrency,
            benchmark_version=args.version,
            timeout_per_scenario=args.timeout,
            seed=args.seed,
            semantic_evaluation=args.semantic_eval,
            api_key=args.api_key,
        )

        print_results(result)

        # Save to file
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = (
                Path("benchmark_results")
                / f"he300_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_data = {
            "batch_id": result.batch_id,
            "timestamp": datetime.now().isoformat(),
            "agent_name": result.agent_name,
            "model": result.model,
            "protocol": result.protocol,
            "accuracy": result.accuracy,
            "total_scenarios": result.total_scenarios,
            "correct": result.correct,
            "errors": result.errors,
            "categories": result.categories,
            "avg_latency_ms": result.avg_latency_ms,
            "processing_time_ms": result.processing_time_ms,
            "random_seed": result.random_seed,
        }

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Results saved to: {output_path}")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
