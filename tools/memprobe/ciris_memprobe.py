"""In-process memory composition probe.

`/proc/PID/smaps` can say how much of a process is anonymous memory, but not who
owns it.  This probe answers that from the inside, on demand, without a restart:
it installs a SIGUSR1 handler that writes a JSON report and goes back to sleep.

Three allocators sit under a CIRIS runtime and they are separately measurable:

* **pymalloc** serves Python objects <=512 bytes out of arenas it mmaps itself,
  so its footprint is invisible to glibc.  `sys._debugmallocstats()` reports it.
* **glibc malloc** serves everything else -- large Python allocations *and* every
  Rust allocation, since Rust's default allocator on Linux is the system one.
  `malloc_info(3)` reports it per-arena, and crucially splits bytes obtained from
  the OS from bytes sitting free in the arena, which is the difference between
  "we allocated this" and "we freed this and glibc kept it".
* **file mappings** (the .so images) are not heap at all and are attributed by
  the out-of-process half, `tools/memory_composition.py`.

Activation is via `sitecustomize.py` in this directory; see that file.
"""

from __future__ import annotations

import ctypes
import gc
import json
import os
import re
import signal
import sys
import tempfile
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Optional

DEFAULT_OUT = "/tmp/ciris_memprobe.{pid}.json"

_installed = False


# --------------------------------------------------------------------------
# glibc malloc
# --------------------------------------------------------------------------


def _malloc_info_xml() -> Optional[str]:
    """Capture malloc_info(3) output.

    malloc_info writes to a FILE*, so we hand it a real temp file through
    fdopen rather than trying to build a stream in Python.
    """
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
    except OSError:
        return None
    if not hasattr(libc, "malloc_info"):
        return None

    libc.fdopen.restype = ctypes.c_void_p
    libc.fdopen.argtypes = [ctypes.c_int, ctypes.c_char_p]
    libc.malloc_info.argtypes = [ctypes.c_int, ctypes.c_void_p]
    libc.fflush.argtypes = [ctypes.c_void_p]

    fd, path = tempfile.mkstemp(prefix="memprobe-malloc-", suffix=".xml")
    try:
        # fdopen takes ownership of fd; do not close it ourselves afterwards.
        stream = libc.fdopen(fd, b"w")
        if not stream:
            os.close(fd)
            return None
        libc.malloc_info(0, stream)
        libc.fflush(stream)
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except Exception:
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _parse_malloc_info(xml: str) -> Dict[str, Any]:
    """Reduce malloc_info XML to the numbers that decide the question.

    The schema is the allocator's, not a standard, so dispatch on it and say so
    when it is one we do not know -- reporting zeros for an unrecognised
    allocator would look exactly like a process that allocates nothing.
    """
    if "<system " in xml:
        return _parse_malloc_info_glibc(xml)
    if 'version="jemalloc' in xml or "<allocated-bins>" in xml:
        return _parse_malloc_info_bionic(xml)
    return {
        "available": False,
        "flavor": "unrecognised",
        "reason": "malloc_info schema not recognised; report the head below",
        "xml_head": xml[:512],
    }


def _parse_malloc_info_glibc(xml: str) -> Dict[str, Any]:
    """glibc reports, per arena and in total, bytes held from the kernel
    (`<system type="current">`) alongside bytes sitting free in bins
    (`<total type="rest">` / `"fast"`).  in_use = system - free is the only
    figure that corresponds to live objects; the remainder is retention.
    """
    heaps: List[Dict[str, int]] = []
    for block in re.findall(r'<heap nr="(\d+)">(.*?)</heap>', xml, re.S):
        nr, body = int(block[0]), block[1]
        heap = {"nr": nr}
        for kind in ("fast", "rest"):
            match = re.search(rf'<total type="{kind}" count="(\d+)" size="(\d+)"', body)
            heap[f"free_{kind}_bytes"] = int(match.group(2)) if match else 0
            heap[f"free_{kind}_count"] = int(match.group(1)) if match else 0
        for kind, key in (("current", "system_current"), ("max", "system_max")):
            match = re.search(rf'<system type="{kind}" size="(\d+)"', body)
            heap[key] = int(match.group(1)) if match else 0
        match = re.search(r'<aspace type="total" size="(\d+)"', body)
        heap["aspace_total"] = int(match.group(1)) if match else 0
        heap["free_bytes"] = heap["free_fast_bytes"] + heap["free_rest_bytes"]
        heap["in_use_bytes"] = max(0, heap["system_current"] - heap["free_bytes"])
        heaps.append(heap)

    tail = xml.rsplit("</heap>", 1)[-1] if "</heap>" in xml else xml
    totals: Dict[str, int] = {}
    for kind in ("fast", "rest", "mmap"):
        match = re.search(rf'<total type="{kind}" count="(\d+)" size="(\d+)"', tail)
        totals[f"{kind}_bytes"] = int(match.group(2)) if match else 0
        totals[f"{kind}_count"] = int(match.group(1)) if match else 0
    match = re.search(r'<system type="current" size="(\d+)"', tail)
    totals["system_current"] = int(match.group(1)) if match else 0
    match = re.search(r'<system type="max" size="(\d+)"', tail)
    totals["system_max"] = int(match.group(1)) if match else 0

    free_bytes = totals["fast_bytes"] + totals["rest_bytes"]
    return {
        "available": True,
        "flavor": "glibc",
        "arenas": len(heaps),
        "system_current_bytes": totals["system_current"],
        "mmapped_bytes": totals["mmap_bytes"],
        "mmapped_count": totals["mmap_count"],
        "free_bytes": free_bytes,
        "in_use_bytes": max(0, totals["system_current"] - free_bytes),
        "retention_ratio": (free_bytes / totals["system_current"]) if totals["system_current"] else 0.0,
        "heaps": sorted(heaps, key=lambda h: -h["system_current"])[:16],
    }


def _parse_malloc_info_bionic(xml: str) -> Dict[str, Any]:
    """Android reports only what is *allocated*, per heap and size class.

    There is no counterpart to glibc's `<system>`, so retention cannot be read
    off directly -- it has to be inferred against anonymous RSS by the caller.
    Reporting only what Bionic actually states keeps that inference honest.
    """
    heaps: List[Dict[str, int]] = []
    for block in re.findall(r'<heap nr="(\d+)">(.*?)</heap>', xml, re.S):
        nr, body = int(block[0]), block[1]
        heap = {"nr": nr}
        for tag, key in (
            ("allocated-large", "allocated_large"),
            ("allocated-huge", "allocated_huge"),
            ("allocated-bins", "allocated_bins"),
            ("bins-total", "bins_total"),
        ):
            match = re.search(rf"<{tag}>(\d+)</{tag}>", body)
            heap[key] = int(match.group(1)) if match else 0
        heap["in_use_bytes"] = heap["allocated_large"] + heap["allocated_huge"] + heap["allocated_bins"]
        heaps.append(heap)

    in_use = sum(h["in_use_bytes"] for h in heaps)
    return {
        "available": True,
        "flavor": "bionic",
        "arenas": len(heaps),
        "in_use_bytes": in_use,
        # Bionic states none of these; leaving them absent rather than zero keeps
        # "not reported" distinguishable from "measured as nothing".
        "system_current_bytes": None,
        "free_bytes": None,
        "mmapped_bytes": None,
        "retention_note": "bionic reports allocated bytes only; infer retention from anonymous RSS",
        "heaps": sorted(heaps, key=lambda h: -h["in_use_bytes"])[:16],
    }


# --------------------------------------------------------------------------
# pymalloc
# --------------------------------------------------------------------------


def _pymalloc_stats() -> Dict[str, Any]:
    """Parse `sys._debugmallocstats()`, which only writes to stderr.

    We dup a temp file over fd 2 for the duration rather than touching
    sys.stderr, because the C function writes to the file descriptor directly.
    """
    if not hasattr(sys, "_debugmallocstats"):
        return {"available": False}

    text = ""
    saved = None
    try:
        with tempfile.TemporaryFile("w+b") as sink:
            saved = os.dup(2)
            os.dup2(sink.fileno(), 2)
            try:
                sys._debugmallocstats()  # type: ignore[attr-defined]
            finally:
                os.dup2(saved, 2)
                os.close(saved)
                saved = None
            sink.seek(0)
            text = sink.read().decode("utf-8", "replace")
    except Exception as exc:
        if saved is not None:
            try:
                os.dup2(saved, 2)
                os.close(saved)
            except OSError:
                pass
        return {"available": False, "error": str(exc)}

    stats: Dict[str, Any] = {"available": True}
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*=\s*([\d,]+)\s*$", line)
        if match:
            key = match.group(1).strip().replace(" ", "_").replace("-", "_")
            stats[key] = int(match.group(2).replace(",", ""))
            continue
        match = re.match(r"^(\d+) arenas \* (\d+) bytes/arena\s*=\s*([\d,]+)", line)
        if match:
            stats["arena_count"] = int(match.group(1))
            stats["arena_size_bytes"] = int(match.group(2))
            stats["arena_total_bytes"] = int(match.group(3).replace(",", ""))
    stats["allocated_blocks"] = sys.getallocatedblocks()
    return stats


# --------------------------------------------------------------------------
# Python object census
# --------------------------------------------------------------------------


def _gc_census(top: int = 25) -> Dict[str, Any]:
    """Count tracked objects by type, and shallow-size the heaviest types.

    getsizeof is shallow, so these bytes under-report containers-of-containers;
    the counts are what identify a runaway population.
    """
    try:
        objects = gc.get_objects()
    except Exception as exc:
        return {"available": False, "error": str(exc)}

    counts: Counter = Counter()
    sizes: Counter = Counter()
    for obj in objects:
        try:
            name = type(obj).__qualname__
            counts[name] += 1
            sizes[name] += sys.getsizeof(obj, 0)
        except Exception:
            continue
    total_shallow = sum(sizes.values())
    del objects

    return {
        "available": True,
        "tracked_objects": sum(counts.values()),
        "shallow_bytes_total": total_shallow,
        "generation_counts": list(gc.get_count()),
        "by_count": [{"type": n, "count": c, "shallow_bytes": sizes[n]} for n, c in counts.most_common(top)],
        "by_bytes": [{"type": n, "shallow_bytes": b, "count": counts[n]} for n, b in sizes.most_common(top)],
    }


def _tracemalloc_top(top: int = 20) -> Dict[str, Any]:
    try:
        import tracemalloc
    except ImportError:
        return {"enabled": False}
    if not tracemalloc.is_tracing():
        return {"enabled": False}
    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    entries = []
    for stat in snapshot.statistics("filename")[:top]:
        frame = stat.traceback[0] if stat.traceback else None
        entries.append(
            {
                "file": frame.filename if frame else "?",
                "size_bytes": stat.size,
                "count": stat.count,
            }
        )
    return {"enabled": True, "traced_bytes": current, "peak_bytes": peak, "top": entries}


def _threads() -> Dict[str, Any]:
    """Thread names as Python sees them, plus every OS thread from /proc.

    The two differ by exactly the threads Python did not create -- which is
    where a native runtime's worker pool shows up.
    """
    python_names: Counter = Counter()
    for thread in threading.enumerate():
        python_names[re.sub(r"[-_]?\d+$", "", thread.name or "?")] += 1

    os_names: Counter = Counter()
    try:
        task_dir = "/proc/self/task"
        for tid in os.listdir(task_dir):
            try:
                with open(os.path.join(task_dir, tid, "comm"), encoding="utf-8") as handle:
                    os_names[handle.read().strip()] += 1
            except OSError:
                continue
    except OSError:
        pass

    return {
        "python_thread_count": threading.active_count(),
        "os_thread_count": sum(os_names.values()),
        "python_by_name": dict(python_names.most_common()),
        "os_by_comm": dict(os_names.most_common()),
    }


def _asyncio_tasks() -> Dict[str, Any]:
    try:
        import asyncio

        # The handler runs in the main thread between bytecodes, so when the
        # loop lives there it is genuinely "running" and get_running_loop works.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop_policy().get_event_loop()
        tasks = asyncio.all_tasks(loop)
    except Exception:
        return {"available": False}
    names: Counter = Counter()
    for task in tasks:
        try:
            names[re.sub(r"[-_]?\d+$", "", task.get_name())] += 1
        except Exception:
            continue
    return {"available": True, "count": len(tasks), "by_name": dict(names.most_common(20))}


def _rss_bytes() -> int:
    try:
        with open("/proc/self/statm", encoding="utf-8") as handle:
            return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return 0


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def collect(census: bool = True) -> Dict[str, Any]:
    """Build the full in-process report."""
    started = time.time()
    xml = _malloc_info_xml()
    report: Dict[str, Any] = {
        "schema": "ciris-memprobe/1",
        "pid": os.getpid(),
        "timestamp": time.time(),
        "python": sys.version.split()[0],
        "rss_bytes": _rss_bytes(),
        "loaded_modules": len(sys.modules),
        "glibc_malloc": _parse_malloc_info(xml) if xml else {"available": False},
        "pymalloc": _pymalloc_stats(),
        "threads": _threads(),
        "asyncio": _asyncio_tasks(),
        "tracemalloc": _tracemalloc_top(),
    }
    report["gc"] = _gc_census() if census else {"available": False, "skipped": True}
    report["collect_seconds"] = round(time.time() - started, 3)
    return report


def dump(path: Optional[str] = None, census: bool = True) -> str:
    out = path or os.environ.get("CIRIS_MEMPROBE_OUT") or DEFAULT_OUT.format(pid=os.getpid())
    report = collect(census=census)
    tmp = f"{out}.partial"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
    os.replace(tmp, out)  # readers never see a half-written report
    return out


def trim() -> Dict[str, Any]:
    """Ask glibc to return free heap to the OS, and measure what came back.

    malloc_trim walks every arena and madvises away whole free pages.  It is the
    difference between "this memory is free" and "this memory is the kernel's
    again", so the delta it produces is the honest answer to how much of the
    resident set is reclaimable without changing a line of allocation behaviour.
    """
    before = _rss_bytes()
    started = time.time()
    returned = -1
    try:
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim.argtypes = [ctypes.c_size_t]
        libc.malloc_trim.restype = ctypes.c_int
        returned = int(libc.malloc_trim(0))
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    elapsed = time.time() - started
    after = _rss_bytes()
    return {
        "available": True,
        "released": bool(returned),
        "rss_before_bytes": before,
        "rss_after_bytes": after,
        "reclaimed_bytes": before - after,
        "seconds": round(elapsed, 3),
    }


def _trim_handler(signum: int, frame: Any) -> None:
    try:
        result = trim()
        out = os.environ.get("CIRIS_MEMPROBE_OUT") or DEFAULT_OUT.format(pid=os.getpid())
        path = f"{out}.trim"
        tmp = f"{path}.partial"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
        os.replace(tmp, path)
        print(f"[memprobe] trim reclaimed {result.get('reclaimed_bytes', 0) / 1048576:.1f} MB", file=sys.stderr)
    except Exception as exc:
        print(f"[memprobe] trim failed: {exc}", file=sys.stderr)


def _handler(signum: int, frame: Any) -> None:
    try:
        census = os.environ.get("CIRIS_MEMPROBE_CENSUS", "1") != "0"
        path = dump(census=census)
        print(f"[memprobe] wrote {path}", file=sys.stderr)
    except Exception as exc:
        print(f"[memprobe] dump failed: {exc}", file=sys.stderr)


def install() -> None:
    """Register the SIGUSR1 handler.  Safe to call more than once."""
    global _installed
    if _installed:
        return
    signal.signal(signal.SIGUSR1, _handler)
    signal.signal(signal.SIGUSR2, _trim_handler)
    _installed = True
    print(f"[memprobe] armed on SIGUSR1 (report) / SIGUSR2 (trim), pid {os.getpid()}", file=sys.stderr)


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, sort_keys=True))
