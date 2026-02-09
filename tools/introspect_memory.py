#!/usr/bin/env python3
"""Introspect Python memory usage of running CIRIS agent."""
import asyncio
import gc
import sys
import tracemalloc
from collections import defaultdict
from typing import Any, Dict, List, Tuple

# Start tracing before any imports
tracemalloc.start(25)


def format_size(size: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def _extract_module_name(filename: str) -> str:
    """Extract module name from filename."""
    if "site-packages" in filename:
        parts = filename.split("site-packages/")[-1].split("/")
        return parts[0] if parts else "unknown"

    if "ciris_engine" in filename:
        parts = filename.split("ciris_engine/")
        if len(parts) > 1:
            subparts = parts[1].split("/")
            return "ciris_engine/" + subparts[0]
        return "ciris_engine"

    if "ciris_adapters" in filename:
        parts = filename.split("ciris_adapters/")
        if len(parts) > 1:
            subparts = parts[1].split("/")
            return "ciris_adapters/" + subparts[0]
        return "ciris_adapters"

    return filename.split("/")[-1] if "/" in filename else filename


def _collect_module_stats(snapshot: Any) -> List[Tuple[str, Dict[str, int]]]:
    """Collect and sort memory stats by module."""
    module_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"size": 0, "count": 0})

    for stat in snapshot.statistics("lineno"):
        frame = stat.traceback[0]
        module = _extract_module_name(frame.filename)
        module_stats[module]["size"] += stat.size
        module_stats[module]["count"] += stat.count

    return sorted(module_stats.items(), key=lambda x: x[1]["size"], reverse=True)


def _collect_type_stats() -> Tuple[Dict[str, int], Dict[str, int]]:
    """Collect object counts and sizes by type."""
    type_counts: Dict[str, int] = {}
    type_sizes: Dict[str, int] = {}

    for obj in gc.get_objects():
        t = type(obj).__name__
        type_counts[t] = type_counts.get(t, 0) + 1
        try:
            type_sizes[t] = type_sizes.get(t, 0) + sys.getsizeof(obj)
        except (TypeError, ValueError):
            pass

    return type_counts, type_sizes


def _collect_pydantic_stats() -> Dict[str, int]:
    """Collect Pydantic model instance counts."""
    pydantic_counts: Dict[str, int] = {}
    for obj in gc.get_objects():
        if hasattr(obj, "model_fields"):  # Pydantic v2
            t = type(obj).__name__
            pydantic_counts[t] = pydantic_counts.get(t, 0) + 1
    return pydantic_counts


def _print_module_stats(sorted_modules: List[Tuple[str, Dict[str, int]]]) -> None:
    """Print module memory statistics."""
    print("\n" + "=" * 70)
    print("TOP 25 MEMORY CONSUMERS BY MODULE")
    print("=" * 70)
    print(f"{'Module':<45} {'Size':>12} {'Objects':>10}")
    print("-" * 70)

    total_traced = 0
    for module, stats in sorted_modules[:25]:
        total_traced += stats["size"]
        print(f"{module[:45]:<45} {format_size(stats['size']):>12} {stats['count']:>10}")

    print("-" * 70)
    print(f"{'TOTAL TRACED':<45} {format_size(total_traced):>12}")


def _print_file_stats(snapshot: Any) -> None:
    """Print top files by memory."""
    print("\n" + "=" * 70)
    print("TOP 10 FILES BY MEMORY")
    print("=" * 70)
    for stat in snapshot.statistics("filename")[:10]:
        short_name = stat.traceback[0].filename.split("/")[-1]
        print(f"{format_size(stat.size):>10} | {stat.count:>6} objects | {short_name}")


def _print_type_stats(type_counts: Dict[str, int], type_sizes: Dict[str, int]) -> None:
    """Print object type statistics."""
    print("\n" + "=" * 70)
    print("TOP 20 OBJECT TYPES BY COUNT")
    print("=" * 70)
    print(f"{'Type':<35} {'Count':>12} {'~Size':>12}")
    print("-" * 70)

    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    for t, count in sorted_types[:20]:
        size = type_sizes.get(t, 0)
        print(f"{t:<35} {count:>12,} {format_size(size):>12}")


def _print_pydantic_stats(pydantic_counts: Dict[str, int]) -> None:
    """Print Pydantic model statistics."""
    print("\n" + "=" * 70)
    print("PYDANTIC MODEL INSTANCES")
    print("=" * 70)

    if pydantic_counts:
        sorted_pydantic = sorted(pydantic_counts.items(), key=lambda x: x[1], reverse=True)
        for t, count in sorted_pydantic[:15]:
            print(f"  {t:<45} {count:>8}")
    else:
        print("  No Pydantic models found in memory")


async def main() -> None:
    print("=" * 70)
    print("PYTHON MEMORY INTROSPECTION")
    print("=" * 70)

    # Now import CIRIS
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

    # Create runtime with minimal config
    print("\n[1/4] Creating runtime...")
    runtime = CIRISRuntime(
        agent_name="memory_test",
        adapter_types=["api"],
        mock_llm=True,
    )

    # Initialize
    print("[2/4] Initializing runtime...")
    await runtime.initialize()
    await asyncio.sleep(2)
    gc.collect()

    print("[3/4] Taking memory snapshot...")
    snapshot = tracemalloc.take_snapshot()

    # Collect and print stats
    sorted_modules = _collect_module_stats(snapshot)
    _print_module_stats(sorted_modules)
    _print_file_stats(snapshot)

    type_counts, type_sizes = _collect_type_stats()
    _print_type_stats(type_counts, type_sizes)

    pydantic_counts = _collect_pydantic_stats()
    _print_pydantic_stats(pydantic_counts)

    # Summary
    current, peak = tracemalloc.get_traced_memory()
    print("\n" + "=" * 70)
    print("TRACEMALLOC SUMMARY")
    print("=" * 70)
    print(f"  Current traced memory: {format_size(current)}")
    print(f"  Peak traced memory:    {format_size(peak)}")

    # Cleanup
    print("\n[4/4] Shutting down runtime...")
    await runtime.shutdown()
    tracemalloc.stop()

    print("\n" + "=" * 70)
    print("INTROSPECTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
