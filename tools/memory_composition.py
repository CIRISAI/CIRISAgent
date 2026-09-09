"""Answer *what* a CIRIS process's resident memory is made of, not just how much.

`tools/memory_benchmark.py` reports a single RSS number.  When that number moved
from 317 MB to 732 MB between releases there was nothing in the repo that could
say which allocator the extra bytes belonged to, so this exists.

Two halves, because no single vantage point sees everything:

* **Out of process** (this module, always available): `/proc/PID/smaps` attributes
  every resident page to a mapping, which cleanly separates file-backed images --
  the .so files, whose 82 MB on disk cost only what is actually touched -- from
  anonymous memory, which is heap.  `/proc/PID/task/*/comm` names every OS thread,
  which is how a native runtime's worker pool announces itself.
* **In process** (`tools/memprobe/`, opt-in): pymalloc and glibc each account for
  their own arenas and neither is visible to the other from outside.  Pass
  `--probe` to SIGUSR1 the target and fold its report in.

Usage:
    python3 -m tools.memory_composition --pid 12345
    python3 -m tools.memory_composition --pid 12345 --probe --json out.json

To make `--probe` work, the target must have been started with the probe armed:
    PYTHONPATH=tools/memprobe CIRIS_MEMPROBE=1 python main.py --adapter api
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

MIB = 1048576.0
KIB = 1024.0

# glibc reserves a 64 MiB region per secondary arena (HEAP_MAX_SIZE on 64-bit)
# and mprotects only the committed prefix, so an arena appears in smaps as a
# small rw-p mapping followed by a large ---p one, together 64 MiB and aligned.
GLIBC_ARENA_RESERVE_KB = 64 * 1024
# A pthread stack is an ordinary anonymous mapping, distinguishable only by the
# PROT_NONE guard page glibc places immediately below it.
MAX_GUARD_KB = 64


# --------------------------------------------------------------------------
# /proc readers
# --------------------------------------------------------------------------


def read_smaps_rollup(pid: int) -> Dict[str, int]:
    """Kernel-computed totals for the whole address space, in kB."""
    out: Dict[str, int] = {}
    try:
        with open(f"/proc/{pid}/smaps_rollup", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                value = value.strip()
                if value.endswith("kB"):
                    out[key.strip()] = int(value[:-2].strip())
    except OSError:
        pass
    return out


def read_status(pid: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.partition(":")
                value = value.strip()
                if value.endswith("kB"):
                    out[key] = int(value[:-2].strip())
                elif key in ("Threads", "Name"):
                    out[key] = int(value) if value.isdigit() else value
    except OSError:
        pass
    return out


def read_smaps(pid: int) -> List[Dict[str, Any]]:
    """One entry per mapping, carrying the fields that matter for attribution."""
    wanted = ("Size", "Rss", "Pss", "Private_Dirty", "Private_Clean", "Shared_Dirty", "Anonymous", "Swap")
    mappings: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    try:
        with open(f"/proc/{pid}/smaps", encoding="utf-8") as handle:
            for line in handle:
                if "-" in line[:20] and " " in line and ":" not in line.split()[0]:
                    parts = line.split(maxsplit=5)
                    if len(parts) >= 5 and "-" in parts[0]:
                        if current is not None:
                            mappings.append(current)
                        start, _, end = parts[0].partition("-")
                        current = {
                            "range": parts[0],
                            "start": int(start, 16),
                            "end": int(end, 16),
                            "perms": parts[1],
                            "path": parts[5].strip() if len(parts) > 5 else "",
                        }
                        continue
                if current is None:
                    continue
                key, _, value = line.partition(":")
                if key in wanted:
                    current[key] = int(value.strip()[:-2].strip())
    except OSError:
        return []
    if current is not None:
        mappings.append(current)
    return mappings


def read_thread_comms(pid: int) -> Counter:
    names: Counter = Counter()
    task_dir = f"/proc/{pid}/task"
    try:
        for tid in os.listdir(task_dir):
            try:
                with open(os.path.join(task_dir, tid, "comm"), encoding="utf-8") as handle:
                    names[handle.read().strip()] += 1
            except OSError:
                continue
    except OSError:
        pass
    return names


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------


def classify(mapping: Dict[str, Any]) -> Tuple[str, str]:
    """Return (class, label) for one mapping, ignoring its neighbours."""
    path = mapping.get("path", "")

    if path == "[heap]":
        return "brk-heap", "[heap] main arena"
    if path == "[stack]":
        return "stack", "[stack] main"
    if path.startswith("[") and path.endswith("]"):
        return "kernel", path
    if not path:
        return "anon", "anon >=4M (large)" if mapping.get("Size", 0) >= 4096 else "anon <4M (small)"

    base = os.path.basename(path)
    if ".so" in base:
        return "lib", base
    if base.endswith((".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3")):
        return "sqlite", base
    if path.startswith("/memfd:") or path.startswith("/dev/shm"):
        return "shm", base
    if path.startswith("/dev/"):
        return "dev", base
    return "file", base


def refine_anonymous(mappings: List[Dict[str, Any]]) -> None:
    """Re-label anonymous mappings using their neighbours.

    Size alone is not enough and guessing from it is actively wrong: a worker
    thread's 8 MiB stack and a worker thread's 8 MiB malloc are the same size.
    What separates them is layout -- glibc puts a PROT_NONE guard page directly
    below every pthread stack, and reserves each secondary arena as one 64 MiB
    aligned span whose untouched tail stays PROT_NONE.  Both are unambiguous in
    the mapping list and neither is visible from a single entry.
    """
    ordered = sorted(mappings, key=lambda m: m.get("start", 0))
    for index, mapping in enumerate(ordered):
        if mapping.get("path") or mapping.get("_class") != "anon":
            continue
        perms = mapping.get("perms", "")
        size_kb = mapping.get("Size", 0)
        prev = ordered[index - 1] if index > 0 else None
        nxt = ordered[index + 1] if index + 1 < len(ordered) else None

        if perms.startswith("rw"):
            # glibc secondary arena: committed prefix of a 64 MiB aligned span.
            if (
                nxt is not None
                and not nxt.get("path")
                and nxt.get("perms", "").startswith("---")
                and nxt.get("start") == mapping.get("end")
                and size_kb + nxt.get("Size", 0) == GLIBC_ARENA_RESERVE_KB
                and mapping.get("start", 1) % (GLIBC_ARENA_RESERVE_KB * 1024) == 0
            ):
                mapping["_label"] = "glibc secondary arena (committed)"
                nxt["_label"] = "glibc secondary arena (reserve)"
                nxt["_class"] = "anon"
                continue
            # pthread stack: guard page directly below.
            if (
                prev is not None
                and not prev.get("path")
                and prev.get("perms", "").startswith("---")
                and prev.get("end") == mapping.get("start")
                and prev.get("Size", 0) <= MAX_GUARD_KB
                and mapping.get("_label") != "glibc secondary arena (committed)"
            ):
                mapping["_class"] = "stack"
                mapping["_label"] = "thread stack"
                prev["_class"] = "stack"
                prev["_label"] = "thread stack guard"


def aggregate(mappings: List[Dict[str, Any]]) -> Dict[str, Any]:
    for mapping in mappings:
        klass, label = classify(mapping)
        mapping["_class"] = klass
        mapping["_label"] = label
    refine_anonymous(mappings)

    by_class: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "size_kb": 0, "rss_kb": 0, "dirty_kb": 0})
    by_label: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "size_kb": 0, "rss_kb": 0, "dirty_kb": 0})
    anon_size_hist: Counter = Counter()

    for mapping in mappings:
        klass = mapping["_class"]
        label = mapping["_label"]
        size_kb = mapping.get("Size", 0)
        rss_kb = mapping.get("Rss", 0)
        dirty_kb = mapping.get("Private_Dirty", 0) + mapping.get("Shared_Dirty", 0)
        for bucket, key in ((by_class, klass), (by_label, f"{klass}:{label}")):
            bucket[key]["count"] += 1
            bucket[key]["size_kb"] += size_kb
            bucket[key]["rss_kb"] += rss_kb
            bucket[key]["dirty_kb"] += dirty_kb
        if klass == "anon":
            anon_size_hist[size_kb] += 1

    return {
        "by_class": dict(by_class),
        "by_label": dict(by_label),
        "anon_size_hist_kb": dict(anon_size_hist.most_common()),
        "mapping_count": len(mappings),
    }


# --------------------------------------------------------------------------
# In-process probe
# --------------------------------------------------------------------------


def trigger_probe(pid: int, out_path: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """SIGUSR1 the target and wait for it to drop a report.

    The probe writes to a `.partial` file and renames, so seeing the path at all
    means the JSON is complete.
    """
    before = os.path.getmtime(out_path) if os.path.exists(out_path) else 0.0
    try:
        os.kill(pid, signal.SIGUSR1)
    except OSError as exc:
        print(f"  probe: cannot signal pid {pid}: {exc}", file=sys.stderr)
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(out_path) and os.path.getmtime(out_path) > before:
            try:
                with open(out_path, encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, ValueError):
                pass
        time.sleep(0.25)
    print(f"  probe: no report at {out_path} within {timeout:.0f}s", file=sys.stderr)
    return None


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _mb(kb: float) -> float:
    return kb / KIB


def render(report: Dict[str, Any], top: int = 20) -> str:
    lines: List[str] = []
    rollup = report["rollup"]
    status = report["status"]
    agg = report["mappings"]
    rss_kb = rollup.get("Rss", status.get("VmRSS", 0))

    def pct(kb: float) -> str:
        return f"{(kb / rss_kb * 100):5.1f}%" if rss_kb else "    - "

    lines.append("=" * 74)
    lines.append(f"MEMORY COMPOSITION - pid {report['pid']} ({status.get('Name', '?')})")
    lines.append("=" * 74)
    lines.append(f"  RSS                {_mb(rss_kb):9.1f} MB     PSS {_mb(rollup.get('Pss', 0)):9.1f} MB")
    lines.append(
        f"  Private_Dirty      {_mb(rollup.get('Private_Dirty', 0)):9.1f} MB"
        f"     Swap {_mb(rollup.get('Swap', 0)):8.1f} MB"
    )
    lines.append(
        f"  Anonymous          {_mb(rollup.get('Anonymous', 0)):9.1f} MB"
        f"     VmSize {_mb(status.get('VmSize', 0)):9.1f} MB (virtual)"
    )
    lines.append(f"  OS threads         {status.get('Threads', 0):9d}        mappings {agg['mapping_count']:6d}")

    lines.append("")
    lines.append("-- resident by class ------------------------------------------------------")
    lines.append(f"  {'class':<14} {'RSS MB':>9} {'  %':>6} {'mapped MB':>10} {'touched':>8} {'n':>6}")
    for klass, vals in sorted(agg["by_class"].items(), key=lambda kv: -kv[1]["rss_kb"]):
        touched = (vals["rss_kb"] / vals["size_kb"] * 100) if vals["size_kb"] else 0.0
        lines.append(
            f"  {klass:<14} {_mb(vals['rss_kb']):9.1f} {pct(vals['rss_kb']):>6} "
            f"{_mb(vals['size_kb']):10.1f} {touched:7.1f}% {vals['count']:6d}"
        )

    lines.append("")
    lines.append(f"-- top {top} mappings by RSS " + "-" * 43)
    lines.append(f"  {'label':<44} {'RSS MB':>9} {'mapped MB':>10}")
    ranked = sorted(agg["by_label"].items(), key=lambda kv: -kv[1]["rss_kb"])[:top]
    for label, vals in ranked:
        lines.append(f"  {label[:44]:<44} {_mb(vals['rss_kb']):9.1f} {_mb(vals['size_kb']):10.1f}")

    lines.append("")
    lines.append("-- OS threads by name -----------------------------------------------------")
    for name, count in report["threads"].items():
        lines.append(f"  {name:<40} {count:6d}")

    probe = report.get("probe")
    if probe:
        lines.append("")
        lines.append("-- allocators (in-process) ------------------------------------------------")
        glibc = probe.get("glibc_malloc", {})
        flavor = glibc.get("flavor", "glibc")
        if not glibc.get("available", glibc.get("arenas") is not None):
            if glibc.get("reason"):
                lines.append(f"  system malloc  UNREADABLE: {glibc['reason']}")
                lines.append(f"                 {glibc.get('xml_head', '')[:120]!r}")
        elif glibc.get("system_current_bytes") is None:
            # Bionic states allocated bytes only.
            lines.append(f"  {flavor} malloc  heaps={glibc['arenas']:<4d} in use {glibc['in_use_bytes'] / MIB:9.1f} MB")
            lines.append(f"                 retention not reported by this allocator; see residual below")
        else:
            lines.append(
                f"  {flavor} malloc   arenas={glibc['arenas']:<4d} "
                f"from OS {glibc['system_current_bytes'] / MIB:9.1f} MB"
            )
            lines.append(
                f"                 in use  {glibc['in_use_bytes'] / MIB:9.1f} MB     "
                f"free but retained {glibc['free_bytes'] / MIB:9.1f} MB ({glibc['retention_ratio'] * 100:.1f}%)"
            )
            lines.append(f"                 mmapped {glibc['mmapped_bytes'] / MIB:9.1f} MB  ({glibc['mmapped_count']} blocks)")
        pym = probe.get("pymalloc", {})
        if pym.get("available"):
            allocated = pym.get("bytes_in_allocated_blocks", 0)
            arena_total = pym.get("arena_total_bytes", 0)
            lines.append(
                f"  pymalloc       arenas={pym.get('arena_count', 0):<4d} "
                f"reserved {arena_total / MIB:9.1f} MB"
            )
            lines.append(
                f"                 in use  {allocated / MIB:9.1f} MB     "
                f"free in arenas    {(arena_total - allocated) / MIB:9.1f} MB"
            )
        census = probe.get("gc", {})
        if census.get("available"):
            lines.append(
                f"  python objects {census['tracked_objects']:>9,d} tracked   "
                f"shallow {census['shallow_bytes_total'] / MIB:9.1f} MB"
            )
        tasks = probe.get("asyncio", {})
        if tasks.get("available"):
            lines.append(f"  asyncio tasks  {tasks.get('count', 0):>9,d}")

        lines.append("")
        lines.append("-- reconciliation ---------------------------------------------------------")

        def row(label: str, kb: float) -> str:
            return f"  {label:<32} {_mb(kb):9.1f} MB {pct(kb)}"

        file_kb = sum(
            vals["rss_kb"] for klass, vals in agg["by_class"].items() if klass in ("lib", "file", "sqlite", "shm", "dev")
        )
        pym_kb = pym.get("arena_total_bytes", 0) / KIB if pym.get("available") else 0
        glibc_use_kb = (glibc.get("in_use_bytes") or 0) / KIB
        glibc_free_kb = (glibc.get("free_bytes") or 0) / KIB
        # Allocations above the mmap threshold bypass the arenas entirely, so
        # they are absent from `system current` and have to be added back.
        glibc_mmap_kb = (glibc.get("mmapped_bytes") or 0) / KIB
        stack_kb = agg["by_class"].get("stack", {}).get("rss_kb", 0)
        accounted = file_kb + pym_kb + glibc_use_kb + glibc_free_kb + glibc_mmap_kb + stack_kb
        lines.append(row("file-backed images (touched)", file_kb))
        lines.append(row("pymalloc arenas (python objects)", pym_kb))
        lines.append(row(f"{flavor} heap, in use", glibc_use_kb))
        if glibc.get("free_bytes") is None:
            lines.append(f"  {'heap free but not returned':<32}    (not reported by this allocator)")
        else:
            lines.append(row("heap free but not returned", glibc_free_kb))
            lines.append(row("heap mmapped blocks (large)", glibc_mmap_kb))
        lines.append(row("thread stacks", stack_kb))
        lines.append(f"  {'-' * 60}")
        lines.append(row("accounted", accounted))
        lines.append(row("residual (RSS - accounted)", rss_kb - accounted))
        lines.append("  note: allocator figures are bytes held from the OS, which for a")
        lines.append("  demand-paged region can exceed what is resident -- expect a small")
        lines.append("  negative residual rather than an exact sum.")

    trim_result = report.get("trim")
    if trim_result and trim_result.get("available"):
        after = report.get("after_trim", {}).get("rollup", {})
        lines.append("")
        lines.append("-- malloc_trim (what is reclaimable in place) -----------------------------")
        lines.append(f"  RSS before                       {trim_result['rss_before_bytes'] / MIB:9.1f} MB")
        lines.append(f"  RSS after                        {trim_result['rss_after_bytes'] / MIB:9.1f} MB")
        lines.append(
            f"  reclaimed                        {trim_result['reclaimed_bytes'] / MIB:9.1f} MB "
            f"in {trim_result['seconds']:.2f}s"
        )
        if after:
            lines.append(f"  (smaps confirms                  {_mb(after.get('Rss', 0)):9.1f} MB)")

    lines.append("=" * 74)
    return "\n".join(lines)


def trigger_trim(pid: int, out_path: str, timeout: float = 60.0) -> Optional[Dict[str, Any]]:
    """SIGUSR2 the target to run malloc_trim, and read back what it reclaimed."""
    path = f"{out_path}.trim"
    before = os.path.getmtime(path) if os.path.exists(path) else 0.0
    try:
        os.kill(pid, signal.SIGUSR2)
    except OSError as exc:
        print(f"  trim: cannot signal pid {pid}: {exc}", file=sys.stderr)
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path) and os.path.getmtime(path) > before:
            try:
                with open(path, encoding="utf-8") as handle:
                    return json.load(handle)
            except (OSError, ValueError):
                pass
        time.sleep(0.25)
    print(f"  trim: no result at {path} within {timeout:.0f}s", file=sys.stderr)
    return None


def collect(pid: int, probe: bool = False, probe_out: Optional[str] = None, trim: bool = False) -> Dict[str, Any]:
    mappings = read_smaps(pid)
    report: Dict[str, Any] = {
        "schema": "ciris-memory-composition/1",
        "pid": pid,
        "timestamp": time.time(),
        "rollup": read_smaps_rollup(pid),
        "status": read_status(pid),
        "mappings": aggregate(mappings),
        "threads": dict(read_thread_comms(pid).most_common()),
    }
    if probe:
        path = probe_out or f"/tmp/ciris_memprobe.{pid}.json"
        report["probe"] = trigger_probe(pid, path)
        if trim:
            # Measured last: trimming changes the process, so everything above
            # describes the untouched steady state.
            report["trim"] = trigger_trim(pid, path)
            report["after_trim"] = {
                "rollup": read_smaps_rollup(pid),
                "mappings": aggregate(read_smaps(pid)),
            }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pid", type=int, required=True, help="target process")
    parser.add_argument("--probe", action="store_true", help="SIGUSR1 the target for allocator detail")
    parser.add_argument("--probe-out", default=None, help="path the probe writes to")
    parser.add_argument(
        "--trim",
        action="store_true",
        help="after reporting, run malloc_trim in the target and measure what it gives back",
    )
    parser.add_argument("--json", dest="json_path", default=None, help="also write the raw report here")
    parser.add_argument("--top", type=int, default=20, help="mappings to list")
    parser.add_argument(
        "--max-rss-mb",
        type=float,
        default=None,
        help="exit non-zero if RSS exceeds this, for use as a regression gate",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(f"/proc/{args.pid}"):
        print(f"no such process: {args.pid}", file=sys.stderr)
        return 2

    report = collect(args.pid, probe=args.probe, probe_out=args.probe_out, trim=args.trim)
    print(render(report, top=args.top))

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
        print(f"\nwrote {args.json_path}")

    if args.max_rss_mb is not None:
        rss_mb = report["rollup"].get("Rss", report["status"].get("VmRSS", 0)) / KIB
        if rss_mb > args.max_rss_mb:
            print(f"\nFAIL: RSS {rss_mb:.1f} MB exceeds budget {args.max_rss_mb:.1f} MB")
            return 1
        print(f"\nOK: RSS {rss_mb:.1f} MB within budget {args.max_rss_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
