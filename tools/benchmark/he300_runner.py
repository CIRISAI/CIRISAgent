#!/usr/bin/env python3
"""
HE-300 Benchmark Runner - Unified Benchmarking Tool

A complete benchmark runner that manages server lifecycle and runs HE-300
benchmarks via CIRISBench API.

Features:
- Automatic server lifecycle (CIRISBench + CIRIS agent)
- Multiple LLM provider support (together, openai, openrouter, anthropic)
- Multiple runs for statistical significance
- Clean database between runs
- Progress reporting and result aggregation

Usage:
    # Run benchmark with Together/Maverick
    python -m tools.benchmark.he300_runner --provider together --model meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8

    # Run with OpenAI
    python -m tools.benchmark.he300_runner --provider openai --model gpt-4o-mini

    # Multiple runs for statistical significance
    python -m tools.benchmark.he300_runner --provider together --model meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8 --runs 5

    # Quick test with fewer scenarios
    python -m tools.benchmark.he300_runner --provider openai --model gpt-4o-mini --scenarios 20

    # Use external servers (skip lifecycle management)
    python -m tools.benchmark.he300_runner --external --agent-url http://127.0.0.1:8100/a2a
"""

import argparse
import asyncio
import json
import logging
import os
import shutil
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths
CIRIS_ROOT = Path(__file__).parent.parent.parent
CIRISBENCH_ROOT = Path("/home/emoore/CIRISBench")
RESULTS_DIR = CIRIS_ROOT / "benchmark_results"

# Default ports
DEFAULT_CIRISBENCH_PORT = 8080
DEFAULT_CIRIS_PORT = 8000  # API port, A2A is on 8100

# Provider configurations
PROVIDER_CONFIGS = {
    "together": {
        "api_base": "https://api.together.xyz/v1",
        "env_key": "TOGETHER_API_KEY",
        "key_file": Path.home() / ".together_key",
    },
    "openai": {
        "api_base": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "key_file": Path.home() / ".openai_key",
    },
    "openrouter": {
        "api_base": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "key_file": Path.home() / ".openrouter_key",
    },
    "anthropic": {
        "api_base": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "key_file": Path.home() / ".anthropic_key",
    },
}


@dataclass
class BenchmarkResult:
    """Results from a single HE-300 benchmark run."""

    batch_id: str
    accuracy: float
    total_scenarios: int
    correct: int
    errors: int
    categories: Dict[str, Dict[str, Any]]
    avg_latency_ms: float
    processing_time_ms: float


@dataclass
class AggregatedResults:
    """Aggregated results from multiple runs."""

    model: str
    provider: str
    runs: int
    mean_accuracy: float
    std_accuracy: float
    individual_accuracies: List[float]
    category_means: Dict[str, float]
    total_time_seconds: float


def get_api_key(provider: str) -> str:
    """Get API key from environment or key file."""
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        raise ValueError(f"Unknown provider: {provider}")

    # Check environment
    if os.environ.get(config["env_key"]):
        return os.environ[config["env_key"]]

    # Check key file
    if config["key_file"].exists():
        return config["key_file"].read_text().strip()

    raise ValueError(
        f"No API key found for {provider}. "
        f"Set {config['env_key']} or create {config['key_file']}"
    )


class ServerManager:
    """Manages CIRISBench and CIRIS server lifecycle."""

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        cirisbench_port: int = DEFAULT_CIRISBENCH_PORT,
        ciris_port: int = DEFAULT_CIRIS_PORT,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.cirisbench_port = cirisbench_port
        self.ciris_port = ciris_port
        self.a2a_port = ciris_port + 100  # A2A runs on port+100

        self.cirisbench_process: Optional[subprocess.Popen] = None
        self.ciris_process: Optional[subprocess.Popen] = None

    def _kill_existing_servers(self):
        """Kill any existing benchmark servers."""
        logger.info("Stopping any existing servers...")
        subprocess.run(
            ["pkill", "-f", "uvicorn engine.api.main:app"],
            capture_output=True,
        )
        subprocess.run(
            ["pkill", "-f", "main.py.*he-300-benchmark"],
            capture_output=True,
        )
        time.sleep(2)

    def _clean_databases(self):
        """Remove CIRIS databases for fresh state."""
        db_dir = CIRIS_ROOT / "data"
        for db_file in ["ciris_engine.db", "ciris_audit.db"]:
            db_path = db_dir / db_file
            if db_path.exists():
                db_path.unlink()
                logger.debug(f"Removed {db_file}")

    def _get_provider_env(self) -> Dict[str, str]:
        """Get environment variables for the provider."""
        config = PROVIDER_CONFIGS.get(self.provider, {})
        env = os.environ.copy()

        # CIRISBench environment
        env["LLM_PROVIDER"] = self.provider
        env["LLM_MODEL"] = self.model
        env["AUTH_ENABLED"] = "false"

        # Provider-specific API key
        if self.provider == "together":
            env["TOGETHER_API_KEY"] = self.api_key
        elif self.provider == "openai":
            env["OPENAI_API_KEY"] = self.api_key
        elif self.provider == "openrouter":
            env["OPENROUTER_API_KEY"] = self.api_key
        elif self.provider == "anthropic":
            env["ANTHROPIC_API_KEY"] = self.api_key

        return env

    def _get_ciris_env(self) -> Dict[str, str]:
        """Get environment variables for CIRIS agent."""
        env = os.environ.copy()
        config = PROVIDER_CONFIGS.get(self.provider, {})

        env["CIRIS_BENCHMARK_MODE"] = "true"
        env["CIRIS_TEMPLATE"] = "he-300-benchmark"
        env["CIRIS_LLM_PROVIDER"] = self.provider
        env["CIRIS_LLM_MODEL_NAME"] = self.model

        # OpenAI-compatible providers use OPENAI_API_BASE
        if self.provider in ("together", "openrouter"):
            env["OPENAI_API_BASE"] = config["api_base"]
            env["OPENAI_API_KEY"] = self.api_key
        elif self.provider == "openai":
            env["OPENAI_API_KEY"] = self.api_key
        elif self.provider == "anthropic":
            env["ANTHROPIC_API_KEY"] = self.api_key

        return env

    async def _wait_for_health(
        self, url: str, name: str, timeout: int = 60
    ) -> bool:
        """Wait for a server to become healthy."""
        async with aiohttp.ClientSession() as session:
            for i in range(timeout):
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            logger.info(f"  {name} ready")
                            return True
                except Exception:
                    pass
                await asyncio.sleep(1)
        return False

    async def start_servers(self, clean_db: bool = True):
        """Start CIRISBench and CIRIS servers."""
        self._kill_existing_servers()

        if clean_db:
            self._clean_databases()

        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        # Start CIRISBench
        logger.info(f"Starting CIRISBench on port {self.cirisbench_port}...")
        cirisbench_log = RESULTS_DIR / "cirisbench_server.log"
        cirisbench_env = self._get_provider_env()

        self.cirisbench_process = subprocess.Popen(
            [
                str(CIRISBENCH_ROOT / ".venv" / "bin" / "python"),
                "-m",
                "uvicorn",
                "engine.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.cirisbench_port),
                "--log-level",
                "warning",
            ],
            cwd=CIRISBENCH_ROOT,
            env=cirisbench_env,
            stdout=open(cirisbench_log, "w"),
            stderr=subprocess.STDOUT,
        )

        # Start CIRIS
        logger.info(f"Starting CIRIS on port {self.ciris_port} (A2A: {self.a2a_port})...")
        ciris_log = RESULTS_DIR / f"ciris_{self.provider}.log"
        ciris_env = self._get_ciris_env()

        self.ciris_process = subprocess.Popen(
            [
                str(CIRIS_ROOT / ".venv" / "bin" / "python"),
                "main.py",
                "--adapter",
                "api",
                "--adapter",
                "a2a",
                "--template",
                "he-300-benchmark",
                "--port",
                str(self.ciris_port),
            ],
            cwd=CIRIS_ROOT,
            env=ciris_env,
            stdout=open(ciris_log, "w"),
            stderr=subprocess.STDOUT,
        )

        # Wait for servers
        logger.info("Waiting for servers to be ready...")
        await asyncio.sleep(5)

        ciris_healthy = await self._wait_for_health(
            f"http://127.0.0.1:{self.a2a_port}/health", "CIRIS A2A"
        )
        if not ciris_healthy:
            raise RuntimeError(
                f"CIRIS failed to start. Check {ciris_log}"
            )

        bench_healthy = await self._wait_for_health(
            f"http://127.0.0.1:{self.cirisbench_port}/health", "CIRISBench"
        )
        if not bench_healthy:
            raise RuntimeError(
                f"CIRISBench failed to start. Check {cirisbench_log}"
            )

        logger.info("All servers ready")

    async def restart_ciris(self, clean_db: bool = True):
        """Restart CIRIS server for clean state between runs."""
        logger.info("Restarting CIRIS for clean state...")

        if self.ciris_process:
            self.ciris_process.terminate()
            try:
                self.ciris_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ciris_process.kill()
            self.ciris_process = None

        subprocess.run(
            ["pkill", "-f", "main.py.*he-300-benchmark"],
            capture_output=True,
        )
        await asyncio.sleep(3)

        if clean_db:
            self._clean_databases()

        ciris_log = RESULTS_DIR / f"ciris_{self.provider}.log"
        ciris_env = self._get_ciris_env()

        self.ciris_process = subprocess.Popen(
            [
                str(CIRIS_ROOT / ".venv" / "bin" / "python"),
                "main.py",
                "--adapter",
                "api",
                "--adapter",
                "a2a",
                "--template",
                "he-300-benchmark",
                "--port",
                str(self.ciris_port),
            ],
            cwd=CIRIS_ROOT,
            env=ciris_env,
            stdout=open(ciris_log, "a"),
            stderr=subprocess.STDOUT,
        )

        await asyncio.sleep(10)

        ciris_healthy = await self._wait_for_health(
            f"http://127.0.0.1:{self.a2a_port}/health", "CIRIS A2A", timeout=60
        )
        if not ciris_healthy:
            raise RuntimeError("CIRIS failed to restart")

        await asyncio.sleep(5)  # Extra settle time

    def stop_servers(self):
        """Stop all servers."""
        logger.info("Stopping servers...")

        if self.ciris_process:
            self.ciris_process.terminate()
            try:
                self.ciris_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.ciris_process.kill()

        if self.cirisbench_process:
            self.cirisbench_process.terminate()
            try:
                self.cirisbench_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.cirisbench_process.kill()


async def run_single_benchmark(
    cirisbench_url: str,
    agent_url: str,
    agent_name: str,
    model: str,
    sample_size: int = 300,
    concurrency: int = 5,
    timeout_per_scenario: float = 120.0,
) -> BenchmarkResult:
    """Run a single benchmark via CIRISBench API."""
    endpoint = f"{cirisbench_url}/he300/agentbeats/run"

    payload = {
        "agent_url": agent_url,
        "agent_name": agent_name,
        "model": model,
        "protocol": "a2a",
        "sample_size": sample_size,
        "concurrency": concurrency,
        "benchmark_version": "1.2",
        "timeout_per_scenario": timeout_per_scenario,
        "semantic_evaluation": False,
    }

    async with aiohttp.ClientSession() as session:
        timeout = aiohttp.ClientTimeout(
            total=timeout_per_scenario * sample_size + 300
        )

        async with session.post(endpoint, json=payload, timeout=timeout) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise Exception(f"CIRISBench error {resp.status}: {error_text[:500]}")

            data = await resp.json()

            return BenchmarkResult(
                batch_id=data.get("batch_id", "unknown"),
                accuracy=data.get("accuracy", 0.0),
                total_scenarios=data.get("total_scenarios", 0),
                correct=data.get("correct", 0),
                errors=data.get("errors", 0),
                categories=data.get("categories", {}),
                avg_latency_ms=data.get("avg_latency_ms", 0.0),
                processing_time_ms=data.get("processing_time_ms", 0.0),
            )


def print_run_result(run_num: int, total_runs: int, result: BenchmarkResult):
    """Print results from a single run."""
    print(f"\n{'━' * 50}")
    print(f"  Run {run_num} of {total_runs}")
    print(f"{'━' * 50}")
    print(f"  Accuracy: {result.accuracy * 100:.1f}% (errors: {result.errors})")

    for cat in ["commonsense", "commonsense_hard", "deontology", "justice", "virtue"]:
        stats = result.categories.get(cat, {})
        if stats.get("total", 0) > 0:
            acc = stats.get("accuracy", 0) * 100
            correct = stats.get("correct", 0)
            total = stats.get("total", 0)
            print(f"    {cat:17}: {acc:.1f}% ({correct}/{total})")


def print_final_results(results: AggregatedResults):
    """Print aggregated results from all runs."""
    print("\n")
    print("=" * 60)
    print("  FINAL RESULTS")
    print("=" * 60)
    print(f"  Model: {results.model}")
    print(f"  Provider: {results.provider}")
    print(f"  Runs: {results.runs}")
    print("-" * 60)

    if results.runs > 1:
        print(f"  Accuracy: {results.mean_accuracy:.1f}% ± {results.std_accuracy:.1f}%")
        print(f"  Individual: {[f'{a:.1f}%' for a in results.individual_accuracies]}")
    else:
        print(f"  Accuracy: {results.mean_accuracy:.1f}%")

    print("-" * 60)
    print("  Category Means:")
    for cat in ["commonsense", "commonsense_hard", "deontology", "justice", "virtue"]:
        if cat in results.category_means:
            print(f"    {cat:17}: {results.category_means[cat]:.1f}%")

    print("-" * 60)
    print(f"  Total Time: {results.total_time_seconds:.1f}s")
    print("=" * 60)


async def run_benchmark(
    provider: str,
    model: str,
    runs: int = 1,
    scenarios: int = 300,
    concurrency: int = 5,
    timeout: float = 120.0,
    external: bool = False,
    agent_url: Optional[str] = None,
    cirisbench_url: Optional[str] = None,
    output_dir: Optional[Path] = None,
) -> AggregatedResults:
    """Run the complete benchmark with server management."""
    start_time = time.time()
    output_dir = output_dir or RESULTS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    agent_name = f"CIRIS + {model.split('/')[-1]}"

    server_manager: Optional[ServerManager] = None
    results: List[BenchmarkResult] = []
    accuracies: List[float] = []
    category_accuracies: Dict[str, List[float]] = {
        "commonsense": [],
        "commonsense_hard": [],
        "deontology": [],
        "justice": [],
        "virtue": [],
    }

    try:
        if external:
            # Use external servers
            if not agent_url:
                agent_url = "http://127.0.0.1:8100/a2a"
            if not cirisbench_url:
                cirisbench_url = "http://127.0.0.1:8080"
            logger.info(f"Using external servers: CIRISBench={cirisbench_url}, Agent={agent_url}")
        else:
            # Manage servers
            api_key = get_api_key(provider)
            server_manager = ServerManager(provider, model, api_key)
            await server_manager.start_servers()
            agent_url = f"http://127.0.0.1:{server_manager.a2a_port}/a2a"
            cirisbench_url = f"http://127.0.0.1:{server_manager.cirisbench_port}"

        print("\n" + "=" * 60)
        print(f"  HE-300 v1.2 Benchmark")
        print(f"  {agent_name}")
        print(f"  {runs} run{'s' if runs > 1 else ''}, {scenarios} scenarios each")
        print("=" * 60)

        for run_num in range(1, runs + 1):
            logger.info(f"Starting run {run_num}/{runs}...")

            result = await run_single_benchmark(
                cirisbench_url=cirisbench_url,
                agent_url=agent_url,
                agent_name=agent_name,
                model=model,
                sample_size=scenarios,
                concurrency=concurrency,
                timeout_per_scenario=timeout,
            )

            results.append(result)
            accuracies.append(result.accuracy * 100)

            for cat in category_accuracies:
                cat_stats = result.categories.get(cat, {})
                if cat_stats.get("total", 0) > 0:
                    category_accuracies[cat].append(cat_stats.get("accuracy", 0) * 100)

            print_run_result(run_num, runs, result)

            # Save individual run result
            run_file = output_dir / f"ciris_{provider}_run{run_num}_{timestamp}.json"
            with open(run_file, "w") as f:
                json.dump(
                    {
                        "run": run_num,
                        "timestamp": datetime.now().isoformat(),
                        "model": model,
                        "provider": provider,
                        "accuracy": result.accuracy,
                        "total_scenarios": result.total_scenarios,
                        "correct": result.correct,
                        "errors": result.errors,
                        "categories": result.categories,
                        "avg_latency_ms": result.avg_latency_ms,
                        "processing_time_ms": result.processing_time_ms,
                    },
                    f,
                    indent=2,
                )

            # Restart CIRIS between runs for clean state
            if run_num < runs and server_manager:
                await server_manager.restart_ciris()

    finally:
        if server_manager:
            server_manager.stop_servers()

    # Aggregate results
    total_time = time.time() - start_time
    mean_acc = statistics.mean(accuracies) if accuracies else 0
    std_acc = statistics.stdev(accuracies) if len(accuracies) > 1 else 0

    category_means = {}
    for cat, accs in category_accuracies.items():
        if accs:
            category_means[cat] = statistics.mean(accs)

    aggregated = AggregatedResults(
        model=model,
        provider=provider,
        runs=runs,
        mean_accuracy=mean_acc,
        std_accuracy=std_acc,
        individual_accuracies=accuracies,
        category_means=category_means,
        total_time_seconds=total_time,
    )

    print_final_results(aggregated)

    # Save aggregated results
    summary_file = output_dir / f"ciris_{provider}_summary_{timestamp}.json"
    with open(summary_file, "w") as f:
        json.dump(
            {
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "provider": provider,
                "runs": runs,
                "scenarios_per_run": scenarios,
                "mean_accuracy": mean_acc,
                "std_accuracy": std_acc,
                "individual_accuracies": accuracies,
                "category_means": category_means,
                "total_time_seconds": total_time,
            },
            f,
            indent=2,
        )

    logger.info(f"Results saved to: {output_dir}")
    return aggregated


async def main():
    parser = argparse.ArgumentParser(
        description="HE-300 Benchmark Runner - Unified Benchmarking Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with Together + Maverick
  python -m tools.benchmark.he300_runner --provider together --model meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8

  # Run 5x for statistical significance
  python -m tools.benchmark.he300_runner --provider openai --model gpt-4o-mini --runs 5

  # Quick test
  python -m tools.benchmark.he300_runner --provider openai --model gpt-4o-mini --scenarios 20

  # Use external servers
  python -m tools.benchmark.he300_runner --external --agent-url http://127.0.0.1:8100/a2a
        """,
    )

    parser.add_argument(
        "--provider",
        choices=["together", "openai", "openrouter", "anthropic"],
        default="together",
        help="LLM provider (default: together)",
    )
    parser.add_argument(
        "--model",
        default="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8",
        help="Model identifier",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of benchmark runs (default: 1)",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=300,
        help="Scenarios per run (default: 300, max: 300)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Parallel requests (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout per scenario in seconds (default: 120)",
    )
    parser.add_argument(
        "--external",
        action="store_true",
        help="Use external servers (skip lifecycle management)",
    )
    parser.add_argument(
        "--agent-url",
        help="Agent A2A URL (for --external mode)",
    )
    parser.add_argument(
        "--cirisbench-url",
        help="CIRISBench URL (for --external mode)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help=f"Output directory (default: {RESULTS_DIR})",
    )

    args = parser.parse_args()

    try:
        await run_benchmark(
            provider=args.provider,
            model=args.model,
            runs=args.runs,
            scenarios=min(args.scenarios, 300),
            concurrency=args.concurrency,
            timeout=args.timeout,
            external=args.external,
            agent_url=args.agent_url,
            cirisbench_url=args.cirisbench_url,
            output_dir=args.output_dir,
        )
    except KeyboardInterrupt:
        logger.info("Benchmark interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
