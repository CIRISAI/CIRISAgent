#!/usr/bin/env python3
"""
HE-300 Benchmark Streaming Debug Script.

Runs the streaming verification module with HE-300 benchmark mode enabled,
printing all DMA prompts to help debug format compliance issues.

Usage:
    python -m tools.qa_runner.scripts.he300_stream_debug [--live]
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from tools.qa_runner.config import QAConfig, QAModule
from tools.qa_runner.runner import QARunner


def main():
    parser = argparse.ArgumentParser(description="HE-300 Benchmark Streaming Debug")
    parser.add_argument("--live", action="store_true", help="Use live LLM (requires OPENAI_API_KEY)")
    parser.add_argument("--port", type=int, default=8080, help="API port (default: 8080)")
    args = parser.parse_args()

    # Build config
    config_kwargs = {
        "base_url": f"http://localhost:{args.port}",
        "api_port": args.port,
        "mock_llm": not args.live,
        "verbose": True,
    }

    # If live mode, get API key from environment
    if args.live:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: --live requires OPENAI_API_KEY environment variable")
            sys.exit(1)
        config_kwargs["live_api_key"] = api_key
        config_kwargs["live_model"] = os.environ.get("OPENAI_MODEL_NAME", "gpt-4o-mini")
        config_kwargs["live_base_url"] = os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1")

    config = QAConfig(**config_kwargs)

    print("\n" + "=" * 80)
    print("🔬 HE-300 BENCHMARK STREAMING DEBUG")
    print("=" * 80)
    print(f"Mode: {'LIVE LLM' if args.live else 'MOCK LLM'}")
    print(f"Template: he-300-benchmark")
    print(f"Benchmark Mode: ENABLED")
    print("=" * 80)
    print("\nThis will print all DMA prompts from the SSE stream.")
    print("Look for the format instructions in the prompts.\n")

    # Run with both HE300_BENCHMARK (for template/mode) and STREAMING (for verification)
    # The HE300_BENCHMARK module sets CIRIS_TEMPLATE=he-300-benchmark and CIRIS_BENCHMARK_MODE=true
    modules = [QAModule.HE300_BENCHMARK, QAModule.STREAMING]
    runner = QARunner(config=config, modules=modules)

    # Run the tests
    success = runner.run(modules)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
