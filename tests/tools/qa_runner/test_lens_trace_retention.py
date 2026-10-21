"""Retention sweep for `/tmp/qa-runner-lens-traces-*` dirs.

Lens trace dirs accumulate at ~50-300MB each per QA run; left unchecked
they fill /tmp and block the host (saw 60MB-free-of-935GB on
2026-05-03 from ~30 accumulated dirs). The runner now prunes old dirs
before creating the new one — this test pins that retention behavior.
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.qa_runner.server import APIServerManager


@pytest.fixture
def tmp_lens_dirs(tmp_path, monkeypatch):
    """Create a stack of fake lens-trace dirs under a sandbox /tmp.

    We monkey-patch glob to scope the retention sweep to the sandbox so
    the test can't accidentally delete real `/tmp/qa-runner-lens-traces-*`
    dirs an operator has on hand.
    """
    sandbox_tmp = tmp_path / "tmp"
    sandbox_tmp.mkdir()

    # Build 8 dirs, oldest first, with monotonically increasing mtimes.
    created: list[Path] = []
    for i in range(8):
        d = sandbox_tmp / f"qa-runner-lens-traces-2026050{i}T120000Z"
        d.mkdir()
        # Touch a marker file so the dir isn't empty (matches real layout).
        (d / "accord-batch-marker.json").write_text("{}")
        # mtime increases with i (older first, newer last).
        atime = mtime = time.time() - (8 - i) * 60
        os.utime(d, (atime, mtime))
        created.append(d)

    # Patch glob to return our sandbox dirs instead of real /tmp.
    import tools.qa_runner.server as srv

    real_glob = srv.__dict__.get("glob")  # noqa: F841 — keep handle if needed

    def _fake_glob_factory(_orig=None):
        def _glob(pattern: str) -> list[str]:
            if pattern == "/tmp/qa-runner-lens-traces-*":
                return [str(p) for p in sandbox_tmp.glob("qa-runner-lens-traces-*")]
            # Defer to real glob for any other pattern (none expected, but
            # be safe).
            import glob as _real_glob

            return _real_glob.glob(pattern)

        return _glob

    # The function imports glob locally — patch sys.modules glob.glob via
    # a wrapper module. Easiest path: monkeypatch glob.glob globally for
    # the duration of the test.
    import glob as _glob_module

    real_glob_glob = _glob_module.glob
    monkeypatch.setattr(_glob_module, "glob", _fake_glob_factory())

    yield sandbox_tmp, created

    # Restore (monkeypatch.setattr handles it but be explicit).
    _glob_module.glob = real_glob_glob


def _make_manager() -> APIServerManager:
    """Minimal APIServerManager — only `console` is touched by the prune
    helper, so we stub it out and skip the heavyweight init path."""
    mgr = APIServerManager.__new__(APIServerManager)
    mgr.console = MagicMock()
    return mgr


def test_prune_keeps_default_4_oldest_drop_when_n_5(tmp_lens_dirs):
    """Default `keep_n=5`. The helper keeps `keep_n - 1 = 4` existing dirs
    so the steady-state population is exactly 5 once the new run's dir
    lands. Older dirs are dropped."""
    sandbox_tmp, created = tmp_lens_dirs
    mgr = _make_manager()

    mgr._prune_lens_trace_dirs()

    surviving = sorted(sandbox_tmp.glob("qa-runner-lens-traces-*"))
    assert len(surviving) == 4, f"expected 4 surviving dirs, got {len(surviving)}"
    # The 4 newest dirs (indices 4..7) survive; oldest (0..3) gone.
    surviving_names = {p.name for p in surviving}
    expected = {created[i].name for i in range(4, 8)}
    assert surviving_names == expected


def test_prune_respects_keep_n_env_override(tmp_lens_dirs, monkeypatch):
    """Operator can set `CIRIS_QA_LENS_TRACE_KEEP_N=10` to retain more
    history (or =3 for less). The helper retains `keep_n - 1` existing
    dirs. With keep_n=3, two existing dirs survive."""
    sandbox_tmp, created = tmp_lens_dirs
    monkeypatch.setenv("CIRIS_QA_LENS_TRACE_KEEP_N", "3")

    mgr = _make_manager()
    mgr._prune_lens_trace_dirs()

    surviving = sorted(sandbox_tmp.glob("qa-runner-lens-traces-*"))
    assert len(surviving) == 2  # keep_n - 1 = 2 existing


def test_prune_disabled_when_keep_n_zero(tmp_lens_dirs, monkeypatch):
    """`CIRIS_QA_LENS_TRACE_KEEP_N=0` disables retention entirely — useful
    for bisecting across many runs where every dir matters."""
    sandbox_tmp, created = tmp_lens_dirs
    monkeypatch.setenv("CIRIS_QA_LENS_TRACE_KEEP_N", "0")

    mgr = _make_manager()
    mgr._prune_lens_trace_dirs()

    surviving = sorted(sandbox_tmp.glob("qa-runner-lens-traces-*"))
    assert len(surviving) == 8  # all 8 originals untouched


def test_prune_handles_invalid_env_value_gracefully(tmp_lens_dirs, monkeypatch):
    """Garbage `CIRIS_QA_LENS_TRACE_KEEP_N` value falls back to default 5."""
    sandbox_tmp, _ = tmp_lens_dirs
    monkeypatch.setenv("CIRIS_QA_LENS_TRACE_KEEP_N", "not-a-number")

    mgr = _make_manager()
    mgr._prune_lens_trace_dirs()

    surviving = sorted(sandbox_tmp.glob("qa-runner-lens-traces-*"))
    assert len(surviving) == 4  # default keep_n=5, keeps 4 existing


def test_prune_no_op_when_under_threshold(tmp_path, monkeypatch):
    """If only 2 dirs exist and keep_n=5, no deletion happens."""
    sandbox_tmp = tmp_path / "tmp"
    sandbox_tmp.mkdir()
    for i in range(2):
        d = sandbox_tmp / f"qa-runner-lens-traces-2026050{i}T120000Z"
        d.mkdir()

    import glob as _glob_module

    real = _glob_module.glob
    monkeypatch.setattr(
        _glob_module,
        "glob",
        lambda p: [str(x) for x in sandbox_tmp.glob("qa-runner-lens-traces-*")] if p == "/tmp/qa-runner-lens-traces-*" else real(p),
    )

    mgr = _make_manager()
    mgr._prune_lens_trace_dirs()

    surviving = sorted(sandbox_tmp.glob("qa-runner-lens-traces-*"))
    assert len(surviving) == 2  # both still present


def test_prune_swallows_per_dir_failures(tmp_lens_dirs, monkeypatch):
    """Per-dir delete failure must not raise — retention is best-effort."""
    sandbox_tmp, _ = tmp_lens_dirs

    import shutil as _shutil

    def _broken_rmtree(path):
        raise OSError("simulated permission denied")

    monkeypatch.setattr(_shutil, "rmtree", _broken_rmtree)

    mgr = _make_manager()
    # Should not raise even though every rmtree call fails.
    mgr._prune_lens_trace_dirs()
