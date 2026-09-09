"""The release path has to be shown to release, not just to run."""

import ctypes
import sys

import pytest

from ciris_engine.logic.utils import memory_release
from ciris_engine.schemas.services.resources_core import MemoryReleaseResult


def _is_glibc_linux() -> bool:
    if not sys.platform.startswith("linux") or memory_release._is_android():
        return False
    try:
        ctypes.CDLL("libc.so.6").gnu_get_libc_version
        return True
    except (OSError, AttributeError):
        return False


def test_release_memory_returns_typed_result():
    result = memory_release.release_memory(trigger="manual")
    assert isinstance(result, MemoryReleaseResult)
    assert result.trigger == "manual"
    assert result.duration_ms >= 0
    assert result.gc_collected >= 0
    if _is_glibc_linux():
        assert result.platform_call == "malloc_trim"


@pytest.mark.skipif(not _is_glibc_linux(), reason="exercises glibc's malloc_trim specifically")
def test_release_memory_reclaims_fragmented_free_heap():
    """Freeing every other small block leaves the heap fragmented: glibc's own
    free() only trims the top, so nothing comes back on its own. malloc_trim
    MADV_DONTNEEDs the whole pages inside those free chunks. If this test
    fails to reclaim, the platform call is not doing its job.
    """
    libc = ctypes.CDLL("libc.so.6")
    libc.malloc.restype = ctypes.c_void_p
    libc.malloc.argtypes = [ctypes.c_size_t]
    libc.free.argtypes = [ctypes.c_void_p]

    block = 16 * 1024
    count = 8192  # 128 MB total, 64 MB of it freed below
    blocks = [libc.malloc(block) for _ in range(count)]
    for ptr in blocks:
        ctypes.memset(ptr, 1, block)  # touch, so the pages are actually resident
    for ptr in blocks[::2]:
        libc.free(ptr)

    result = memory_release.release_memory(trigger="test")
    assert result.platform_call == "malloc_trim"
    assert result.reclaimed_mb >= 20, f"expected a real reclaim from 64 MB of fragmented free heap, got {result}"

    for ptr in blocks[1::2]:
        libc.free(ptr)


def test_release_memory_is_safe_on_an_unknown_platform(monkeypatch):
    monkeypatch.setattr(memory_release.sys, "platform", "win32")
    monkeypatch.setattr(memory_release, "_libc", None)
    monkeypatch.setattr(memory_release, "_libc_failed", False)
    monkeypatch.setattr(memory_release, "_is_android", lambda: False)
    result = memory_release.release_memory(trigger="manual")
    assert result.platform_call == "none"
    assert result.gc_collected >= 0


def test_release_memory_survives_a_failing_allocator_call(monkeypatch):
    class BrokenLibc:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    monkeypatch.setattr(memory_release, "_load_libc", lambda: BrokenLibc())
    result = memory_release.release_memory(trigger="manual")
    assert result.platform_call.startswith("unavailable:")
