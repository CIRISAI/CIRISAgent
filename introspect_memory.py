#!/usr/bin/env python3
"""Introspect Python memory usage of running CIRIS agent."""
import asyncio
import gc
import sys
import tracemalloc
from collections import defaultdict

# Start tracing before any imports
tracemalloc.start(25)


def format_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


async def main():
    print("=" * 70)
    print("PYTHON MEMORY INTROSPECTION")
    print("=" * 70)

    # Now import CIRIS
    from ciris_engine.logic.adapters.api.app import create_app
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

    # Let it settle
    await asyncio.sleep(2)

    # Force garbage collection
    gc.collect()

    print("[3/4] Taking memory snapshot...")
    snapshot = tracemalloc.take_snapshot()

    print("\n" + "=" * 70)
    print("TOP 25 MEMORY CONSUMERS BY MODULE")
    print("=" * 70)

    # Group by module
    module_stats = defaultdict(lambda: {"size": 0, "count": 0})

    for stat in snapshot.statistics("lineno"):
        frame = stat.traceback[0]
        filename = frame.filename

        # Extract module name
        if "site-packages" in filename:
            parts = filename.split("site-packages/")[-1].split("/")
            module = parts[0] if parts else "unknown"
        elif "ciris_engine" in filename:
            parts = filename.split("ciris_engine/")
            if len(parts) > 1:
                subparts = parts[1].split("/")
                module = "ciris_engine/" + subparts[0]
            else:
                module = "ciris_engine"
        elif "ciris_adapters" in filename:
            parts = filename.split("ciris_adapters/")
            if len(parts) > 1:
                subparts = parts[1].split("/")
                module = "ciris_adapters/" + subparts[0]
            else:
                module = "ciris_adapters"
        else:
            module = filename.split("/")[-1] if "/" in filename else filename

        module_stats[module]["size"] += stat.size
        module_stats[module]["count"] += stat.count

    # Sort by size
    sorted_modules = sorted(module_stats.items(), key=lambda x: x[1]["size"], reverse=True)

    print(f"{'Module':<45} {'Size':>12} {'Objects':>10}")
    print("-" * 70)
    total_traced = 0
    for module, stats in sorted_modules[:25]:
        total_traced += stats["size"]
        print(f"{module[:45]:<45} {format_size(stats['size']):>12} {stats['count']:>10}")

    print("-" * 70)
    print(f"{'TOTAL TRACED':<45} {format_size(total_traced):>12}")

    # Top allocations by file
    print("\n" + "=" * 70)
    print("TOP 10 FILES BY MEMORY")
    print("=" * 70)
    file_stats = snapshot.statistics("filename")[:10]
    for stat in file_stats:
        short_name = stat.traceback[0].filename.split("/")[-1]
        print(f"{format_size(stat.size):>10} | {stat.count:>6} objects | {short_name}")

    # Memory by type
    print("\n" + "=" * 70)
    print("TOP 20 OBJECT TYPES BY COUNT")
    print("=" * 70)
    type_counts = {}
    type_sizes = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        type_counts[t] = type_counts.get(t, 0) + 1
        try:
            type_sizes[t] = type_sizes.get(t, 0) + sys.getsizeof(obj)
        except:
            pass

    sorted_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    print(f"{'Type':<35} {'Count':>12} {'~Size':>12}")
    print("-" * 70)
    for t, count in sorted_types[:20]:
        size = type_sizes.get(t, 0)
        print(f"{t:<35} {count:>12,} {format_size(size):>12}")

    # Pydantic models specifically
    print("\n" + "=" * 70)
    print("PYDANTIC MODEL INSTANCES")
    print("=" * 70)
    pydantic_counts = {}
    for obj in gc.get_objects():
        if hasattr(obj, "model_fields"):  # Pydantic v2
            t = type(obj).__name__
            pydantic_counts[t] = pydantic_counts.get(t, 0) + 1

    if pydantic_counts:
        sorted_pydantic = sorted(pydantic_counts.items(), key=lambda x: x[1], reverse=True)
        for t, count in sorted_pydantic[:15]:
            print(f"  {t:<45} {count:>8}")
    else:
        print("  No Pydantic models found in memory")

    # Current vs peak
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
