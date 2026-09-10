"""The release path has to be shown to release, not just to run."""

import ctypes
import sys
import types

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


# ---------------------------------------------------------------------------
# Platform dispatch. These exercise the *choice* of allocator call with fake
# libc objects; the real calls are covered by the glibc test above and, for the
# phones, by the five-platform gates.
# ---------------------------------------------------------------------------


class _FakeLibc:
    """Records mallopt/trim/relief calls; `symbols` controls what exists."""

    def __init__(self, symbols, mallopt_results=None):
        self._symbols = set(symbols)
        self.calls = []
        self._mallopt_results = list(mallopt_results or [])

    def __getattr__(self, name):
        if name not in self._symbols:
            raise AttributeError(name)
        fake = self

        class _Fn:
            argtypes = None
            restype = None

            def __call__(self, *args):
                fake.calls.append((name, args))
                if name == "mallopt" and fake._mallopt_results:
                    return fake._mallopt_results.pop(0)
                return 0

        return _Fn()


def _use(monkeypatch, libc, *, platform="linux", android=False):
    monkeypatch.setattr(memory_release.sys, "platform", platform)
    monkeypatch.setattr(memory_release, "_is_android", lambda: android)
    monkeypatch.setattr(memory_release, "_load_libc", lambda: libc)


def test_android_prefers_purge_all_when_the_device_has_it(monkeypatch):
    libc = _FakeLibc({"mallopt"}, mallopt_results=[1])
    _use(monkeypatch, libc, android=True)
    assert memory_release._platform_release() == "mallopt(M_PURGE_ALL)"
    assert libc.calls == [("mallopt", (memory_release._BIONIC_M_PURGE_ALL, 0))]


def test_android_falls_back_to_purge_on_older_api_levels(monkeypatch):
    """M_PURGE_ALL is API 34; an older Bionic returns 0 and we try M_PURGE (API 28)."""
    libc = _FakeLibc({"mallopt"}, mallopt_results=[0, 1])
    _use(monkeypatch, libc, android=True)
    assert memory_release._platform_release() == "mallopt(M_PURGE)"
    assert [c[1][0] for c in libc.calls] == [memory_release._BIONIC_M_PURGE_ALL, memory_release._BIONIC_M_PURGE]


def test_android_without_mallopt_reports_unavailable(monkeypatch):
    _use(monkeypatch, _FakeLibc(set()), android=True)
    assert memory_release._platform_release() == "unavailable:no mallopt"


def test_darwin_uses_malloc_zone_pressure_relief(monkeypatch):
    libc = _FakeLibc({"malloc_zone_pressure_relief"})
    _use(monkeypatch, libc, platform="darwin")
    assert memory_release._platform_release() == "malloc_zone_pressure_relief"
    assert libc.calls[0][0] == "malloc_zone_pressure_relief"


def test_ios_is_darwin_for_this_purpose(monkeypatch):
    _use(monkeypatch, _FakeLibc({"malloc_zone_pressure_relief"}), platform="ios")
    assert memory_release._platform_release() == "malloc_zone_pressure_relief"


def test_darwin_without_the_symbol_reports_unavailable(monkeypatch):
    _use(monkeypatch, _FakeLibc(set()), platform="darwin")
    assert memory_release._platform_release() == "unavailable:no malloc_zone_pressure_relief"


def test_linux_without_malloc_trim_reports_unavailable(monkeypatch):
    _use(monkeypatch, _FakeLibc(set()), platform="linux")
    assert memory_release._platform_release() == "unavailable:no malloc_trim"


def test_no_libc_at_all_is_none(monkeypatch):
    _use(monkeypatch, None, platform="linux")
    assert memory_release._platform_release() == "none"


def test_load_libc_tries_each_candidate_and_remembers_failure(monkeypatch):
    attempts = []

    def fake_cdll(name):
        attempts.append(name)
        raise OSError("nope")

    monkeypatch.setattr(memory_release.ctypes, "CDLL", fake_cdll)
    monkeypatch.setattr(memory_release, "_libc", None)
    monkeypatch.setattr(memory_release, "_libc_failed", False)
    monkeypatch.setattr(memory_release, "_is_android", lambda: False)
    monkeypatch.setattr(memory_release.sys, "platform", "darwin")
    assert memory_release._load_libc() is None
    assert attempts == ["libSystem.B.dylib", None]
    # Second call must not retry: a failed dlopen is not going to start working.
    assert memory_release._load_libc() is None
    assert attempts == ["libSystem.B.dylib", None]


def test_load_libc_picks_bionic_name_on_android(monkeypatch):
    seen = []
    monkeypatch.setattr(memory_release.ctypes, "CDLL", lambda name: seen.append(name) or object())
    monkeypatch.setattr(memory_release, "_libc", None)
    monkeypatch.setattr(memory_release, "_libc_failed", False)
    monkeypatch.setattr(memory_release, "_is_android", lambda: True)
    assert memory_release._load_libc() is not None
    assert seen == ["libc.so"]


def test_rss_bytes_falls_back_to_psutil_without_procfs(monkeypatch):
    """No /proc (macOS, Windows) -> psutil. psutil itself reads /proc on Linux,
    so the fallback is proven with a fake module rather than by starving open()."""
    import builtins
    import sys
    import types

    real_open = builtins.open

    def no_procfs(path, *a, **k):
        if str(path).startswith("/proc/"):
            raise OSError("no procfs")
        return real_open(path, *a, **k)

    fake_psutil = types.ModuleType("psutil")
    fake_psutil.Process = lambda: types.SimpleNamespace(memory_info=lambda: types.SimpleNamespace(rss=123456789))
    monkeypatch.setattr(builtins, "open", no_procfs)
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    assert memory_release.rss_bytes() == 123456789


def test_rss_bytes_is_zero_when_nothing_can_answer(monkeypatch):
    import builtins
    import sys

    monkeypatch.setattr(builtins, "open", lambda *a, **k: (_ for _ in ()).throw(OSError("no procfs")))
    monkeypatch.setitem(sys.modules, "psutil", None)  # import psutil -> ImportError
    assert memory_release.rss_bytes() == 0


def test_is_android_detection_reads_the_environment(monkeypatch):
    monkeypatch.delenv("ANDROID_ROOT", raising=False)
    monkeypatch.delenv("ANDROID_DATA", raising=False)
    monkeypatch.delattr(memory_release.sys, "getandroidapilevel", raising=False)
    assert memory_release._is_android() is False
    monkeypatch.setenv("ANDROID_DATA", "/data")
    assert memory_release._is_android() is True


def test_windows_uses_heapmin_and_trims_the_working_set(monkeypatch):
    """The Windows leg of the modular gate returned platform_call=none: a Windows
    desktop was getting gc.collect() and nothing else."""
    libc = _FakeLibc({"_heapmin"})
    _use(monkeypatch, libc, platform="win32")
    calls = []

    class _WinFn:
        argtypes = None
        restype = None

        def __call__(self, *a):
            calls.append(a)
            return 1

    kernel32 = types.SimpleNamespace(SetProcessWorkingSetSize=_WinFn(), GetCurrentProcess=lambda: 42)
    monkeypatch.setattr(memory_release.ctypes, "windll", types.SimpleNamespace(kernel32=kernel32), raising=False)
    assert memory_release._platform_release() == "_heapmin+SetProcessWorkingSetSize"
    assert libc.calls[0][0] == "_heapmin"
    assert calls and calls[0][0] == 42


def test_windows_without_kernel32_still_heapmins(monkeypatch):
    libc = _FakeLibc({"_heapmin"})
    _use(monkeypatch, libc, platform="win32")
    monkeypatch.delattr(memory_release.ctypes, "windll", raising=False)
    assert memory_release._platform_release() == "_heapmin"


def test_windows_without_heapmin_reports_unavailable(monkeypatch):
    _use(monkeypatch, _FakeLibc(set()), platform="win32")
    assert memory_release._platform_release() == "unavailable:no _heapmin"


def test_load_libc_tries_ucrtbase_then_msvcrt_on_windows(monkeypatch):
    seen = []

    def fake_cdll(name):
        seen.append(name)
        if name == "ucrtbase":
            raise OSError("not found")
        return object()

    monkeypatch.setattr(memory_release.ctypes, "CDLL", fake_cdll)
    monkeypatch.setattr(memory_release, "_libc", None)
    monkeypatch.setattr(memory_release, "_libc_failed", False)
    monkeypatch.setattr(memory_release, "_is_android", lambda: False)
    monkeypatch.setattr(memory_release.sys, "platform", "win32")
    assert memory_release._load_libc() is not None
    assert seen == ["ucrtbase", "msvcrt"]
