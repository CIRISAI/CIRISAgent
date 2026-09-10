"""Hand freed memory back to the operating system.

Freeing memory in Python, or in the Rust substrate folded into the process,
does not return it to the OS: every allocator keeps what it was given and
serves later requests from it. On a server that is a reasonable trade. On a
2 GB phone it is the difference between shrinking when asked and being killed
— at an 822 MB plateau, 347 MB of the agent's resident set was memory glibc
had already been told was free (CIRISServer#577 has the measurement).

This is the one place that knows how to ask each allocator for it back. It is
deliberately a plain synchronous function with no dependency on the runtime:
the host callbacks that need it most (Android onTrimMemory, the iOS watchdog
thread) fire on foreign threads, sometimes while the event loop is frozen.

Platform calls, each documented by its platform and verified against its
header where one was available:

  glibc   malloc_trim(0)                      walks every arena, MADV_DONTNEEDs
                                              whole free pages — not just the top
  Bionic  mallopt(M_PURGE_ALL) / mallopt(M_PURGE)
                                              API 34 / API 28; unknown options are
                                              a harmless no-op on older devices
  Darwin  malloc_zone_pressure_relief(NULL, 0) what the OS itself calls on a
                                              memory warning
  Windows _heapmin() + SetProcessWorkingSetSize  the CRT heap CPython sits on
                                              gives back its free pages; the
                                              working-set call then lets the
                                              kernel trim what is no longer used
"""

from __future__ import annotations

import ctypes
import gc
import logging
import os
import sys
import time
from typing import Optional

from ciris_engine.schemas.services.resources_core import MemoryReleaseResult

logger = logging.getLogger(__name__)

# Bionic mallopt options, from the NDK's <malloc.h>.
_BIONIC_M_PURGE = -101  # API 28
_BIONIC_M_PURGE_ALL = -104  # API 34

_libc: Optional[ctypes.CDLL] = None
_libc_failed = False


def _is_android() -> bool:
    # Kept local so this module stays importable before the engine is.
    return bool(os.getenv("ANDROID_ROOT") or os.getenv("ANDROID_DATA") or hasattr(sys, "getandroidapilevel"))


def _load_libc() -> Optional[ctypes.CDLL]:
    global _libc, _libc_failed
    if _libc is not None or _libc_failed:
        return _libc
    candidates: list[Optional[str]]
    if _is_android():
        candidates = ["libc.so"]
    elif sys.platform.startswith("linux"):
        candidates = ["libc.so.6"]
    elif sys.platform in ("darwin", "ios"):
        candidates = ["libSystem.B.dylib", None]
    elif sys.platform == "win32":
        # ucrtbase is the Universal CRT every supported CPython links against;
        # msvcrt is the legacy fallback and still exports _heapmin.
        candidates = ["ucrtbase", "msvcrt"]
    else:
        candidates = []
    for name in candidates:
        try:
            _libc = ctypes.CDLL(name)
            return _libc
        except OSError:
            continue
    _libc_failed = True
    return None


def rss_bytes() -> int:
    """Resident set size of this process, cheaply, without psutil where possible."""
    try:
        with open("/proc/self/statm", encoding="utf-8") as handle:
            return int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        pass
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except Exception:
        return 0


def _release_bionic(libc: ctypes.CDLL) -> str:
    if not hasattr(libc, "mallopt"):
        return "unavailable:no mallopt"
    libc.mallopt.argtypes = [ctypes.c_int, ctypes.c_int]
    libc.mallopt.restype = ctypes.c_int
    # Newest first; an unrecognised option returns 0 and does nothing.
    if libc.mallopt(_BIONIC_M_PURGE_ALL, 0):
        return "mallopt(M_PURGE_ALL)"
    libc.mallopt(_BIONIC_M_PURGE, 0)
    return "mallopt(M_PURGE)"


def _release_glibc(libc: ctypes.CDLL) -> str:
    if not hasattr(libc, "malloc_trim"):
        return "unavailable:no malloc_trim"
    libc.malloc_trim.argtypes = [ctypes.c_size_t]
    libc.malloc_trim.restype = ctypes.c_int
    libc.malloc_trim(0)
    return "malloc_trim"


def _release_darwin(libc: ctypes.CDLL) -> str:
    if not hasattr(libc, "malloc_zone_pressure_relief"):
        return "unavailable:no malloc_zone_pressure_relief"
    libc.malloc_zone_pressure_relief.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    libc.malloc_zone_pressure_relief.restype = ctypes.c_size_t
    libc.malloc_zone_pressure_relief(None, 0)
    return "malloc_zone_pressure_relief"


def _trim_windows_working_set() -> bool:
    """SetProcessWorkingSetSize(-1, -1): empties the WHOLE working set, live pages
    included (the gate measured 279 -> 1 MB). Returns False when kernel32 is not
    reachable or the call fails; never raises."""
    kernel32 = getattr(getattr(ctypes, "windll", None), "kernel32", None)
    if kernel32 is None:
        return False
    try:
        kernel32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t]
        kernel32.SetProcessWorkingSetSize.restype = ctypes.c_int
        everything = ctypes.c_size_t(-1).value
        kernel32.SetProcessWorkingSetSize(kernel32.GetCurrentProcess(), everything, everything)
        return True
    except Exception:
        return False


def _release_windows(libc: ctypes.CDLL, trigger: str) -> str:
    if not hasattr(libc, "_heapmin"):
        return "unavailable:no _heapmin"
    libc._heapmin.argtypes = []
    libc._heapmin.restype = ctypes.c_int
    libc._heapmin()
    # Returning heap pages is only half of it on Windows: the working set keeps
    # them resident until the kernel is told it may trim. But that trim evicts
    # live pages too, so only when the host itself is asking.
    if trigger.startswith("host:") and _trim_windows_working_set():
        return "_heapmin+SetProcessWorkingSetSize"
    return "_heapmin"


def _platform_release(trigger: str = "manual") -> str:
    """Ask the system allocator to return free pages. Never raises.

    `trigger` matters on Windows only: emptying the working set is right when
    the HOST asks for memory and too blunt for our own threshold -- it evicts
    live pages too, which then soft-fault back in, so on a desktop that would
    be a fault storm every time the warning trips.
    """
    libc = _load_libc()
    if libc is None:
        return "none"
    try:
        if _is_android():
            return _release_bionic(libc)
        if sys.platform.startswith("linux"):
            return _release_glibc(libc)
        if sys.platform in ("darwin", "ios"):
            return _release_darwin(libc)
        if sys.platform == "win32":
            return _release_windows(libc, trigger)
    except Exception as exc:  # an allocator call must never take the process down
        return f"unavailable:{type(exc).__name__}"
    return "none"


def release_memory(trigger: str = "manual") -> MemoryReleaseResult:
    """Collect garbage, then hand the allocators' free pages back to the OS.

    Safe to call from any thread; holds the GIL for the duration of
    gc.collect(), which on a loaded agent is on the order of 100 ms.
    """
    started = time.perf_counter()
    before = rss_bytes()
    collected = gc.collect()
    call = _platform_release(trigger)
    after = rss_bytes()
    result = MemoryReleaseResult(
        trigger=trigger,
        platform_call=call,
        rss_before_mb=before // (1024 * 1024),
        rss_after_mb=after // (1024 * 1024),
        reclaimed_mb=(before - after) // (1024 * 1024),
        gc_collected=collected,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    logger.info(
        "memory release (%s): rss %d -> %d MB, reclaimed %d MB via %s, gc freed %d objects, %d ms",
        result.trigger,
        result.rss_before_mb,
        result.rss_after_mb,
        result.reclaimed_mb,
        result.platform_call,
        result.gc_collected,
        result.duration_ms,
    )
    return result
