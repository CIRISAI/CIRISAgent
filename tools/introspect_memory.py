#!/usr/bin/env python3
"""Introspect Python memory usage of running CIRIS agent.

Usage:
    python3 tools/introspect_memory.py [--adapters ADAPTERS] [--duration SECONDS]

Options:
    --adapters   Adapter to use (default: cli)
    --duration   Seconds to run before shutdown (default: 30)

Example:
    python3 tools/introspect_memory.py
    python3 tools/introspect_memory.py --adapters api --duration 45
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


def format_size(size: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def get_process_memory(pid: int) -> int:
    """Get RSS memory for a process in bytes."""
    try:
        import psutil

        process = psutil.Process(pid)
        return process.memory_info().rss
    except ImportError:
        try:
            with open(f"/proc/{pid}/statm") as f:
                pages = int(f.read().split()[1])
                return pages * os.sysconf("SC_PAGE_SIZE")
        except Exception:
            return 0
    except Exception:
        return 0


def get_children_memory(pid: int) -> int:
    """Get total RSS memory for a process and all its children."""
    try:
        import psutil

        parent = psutil.Process(pid)
        total = parent.memory_info().rss
        for child in parent.children(recursive=True):
            try:
                total += child.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return total
    except ImportError:
        return get_process_memory(pid)
    except Exception:
        return 0


def main(adapters: str = "cli", duration: int = 30) -> int:
    print("=" * 70)
    print("CIRIS 2.0 MEMORY INTROSPECTION")
    print("=" * 70)
    print(f"Adapters: {adapters}")
    print(f"Duration: {duration}s")

    project_root = Path(__file__).parent.parent
    main_py = project_root / "main.py"

    if not main_py.exists():
        print(f"ERROR: main.py not found at {main_py}")
        return 1

    # Match the working command: python3 main.py --adapter cli --mock-llm --timeout 30
    cmd = [
        sys.executable,
        str(main_py),
        "--adapter",
        adapters,
        "--mock-llm",
        "--timeout",
        str(duration),
    ]

    print(f"\nCommand: {' '.join(cmd)}")
    print(f"\n[1/3] Starting CIRIS agent...")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(project_root),
        env=env,
        text=True,
    )

    pid = process.pid
    print(f"PID: {pid}")

    print(f"\n[2/3] Monitoring memory for ~{duration}s...")
    samples = []
    start_time = time.time()

    try:
        while process.poll() is None:
            mem = get_children_memory(pid)
            if mem > 0:
                samples.append(mem)
                elapsed = time.time() - start_time
                print(f"  {elapsed:5.1f}s: {format_size(mem)}", end="\r")
            time.sleep(0.1)  # Sample every 100ms for better resolution

        print()  # newline after progress

        # Process exited
        exit_code = process.returncode
        print(f"\n[3/3] Process exited with code: {exit_code}")

        # Print summary
        print("\n" + "=" * 70)
        print("MEMORY SUMMARY")
        print("=" * 70)
        if samples:
            initial = samples[0] if samples else 0
            peak = max(samples) if samples else 0
            final = samples[-1] if samples else 0
            avg = sum(samples) / len(samples) if samples else 0

            print(f"  Initial:    {format_size(initial)}")
            print(f"  Peak:       {format_size(peak)}")
            print(f"  Final:      {format_size(final)}")
            print(f"  Average:    {format_size(avg)}")
            print(f"  Samples:    {len(samples)}")
        else:
            print("  No memory samples collected")
        print()
        print(f"  Adapters:   {adapters}")
        print(f"  Mock LLM:   True")
        print(f"  Duration:   {duration}s")
        print("\n" + "=" * 70)
        print("INTROSPECTION COMPLETE")
        print("=" * 70)
        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        process.terminate()
        process.wait(timeout=5)
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CIRIS memory introspection tool")
    parser.add_argument(
        "--adapters",
        default="cli",
        help="Adapter to use (default: cli)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Seconds to run before shutdown (default: 30)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(main(adapters=args.adapters, duration=args.duration))
