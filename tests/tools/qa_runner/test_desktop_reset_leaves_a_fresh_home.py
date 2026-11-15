"""Between the no-AI and with-AI legs the desktop home is either fully fresh or the run says it is not.

Five-platform run 43754658996 (2.22.1, ciris-server 0.5.248) failed on every
desktop for one reason: the harness tested on a half-wiped home.

- Windows: the client's factory reset removed 7 entries while the node held the
  rest open (``wipeLocalData -> false``). The kept Ed25519 seed met a new ML-DSA
  seed, so the node re-keyed under its old id and the canonical refused it as
  pubkey_swap. The reset step passed, because the .env was one of the 7.
- macOS: in the gap after reset, the restarted app launched its own
  ciris-server, which reached the canonical and was then killed. The bring-up
  wiped ``data/`` but kept ``identity/``, so the real node came back with the
  same key on a new transport identity (CIRISEdge#1004).
- Linux: the logout ran while the app was still composing after sign-in, missed
  every route once, and failed.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

web_ui = importlib.import_module("tools.qa_runner.modules.web_ui.__main__")
shell_nav_tests = importlib.import_module("tests.tools.qa_runner.test_shell_nav")

WINDOWS_RESET = """\
[CIRISApp] [INFO][onResetSetup] User initiated device reset \u2014 wiping local data
[CIRISApp] [INFO][onResetSetup] attached backend at http://127.0.0.1:4243 is still answering
[LocalDataWipe] could not remove D:\\a\\_temp\\ciris-windows\\data
[LocalDataWipe] D:\\a\\_temp\\ciris-windows: removed 7 generated entries, ok=false
[LocalDataWipe] cleared 0 secure preference(s)
[CIRISApp] [INFO][onResetSetup] wipeLocalData -> false
"""

MACOS_RESET = """\
[CIRISApp] [INFO][onResetSetup] User initiated device reset \u2014 wiping local data
[LocalDataWipe] /Users/runner/work/_temp/ciris-macos: removed 8 generated entries, ok=true
[LocalDataWipe] cleared 0 secure preference(s)
[CIRISApp] [INFO][onResetSetup] wipeLocalData -> true
"""


# ─── 1. a failed client wipe fails the reset ────────────────────────────────


def test_a_partial_client_wipe_is_reported_as_unfinished():
    wiped, lines = web_ui._client_wipe_outcome(WINDOWS_RESET)
    assert wiped is False
    assert any("ok=false" in ln for ln in lines) and any("could not remove" in ln for ln in lines)


def test_a_complete_client_wipe_is_reported_as_finished():
    wiped, lines = web_ui._client_wipe_outcome(MACOS_RESET)
    assert wiped is True and any("ok=true" in ln for ln in lines)


def test_only_the_last_reset_counts():
    assert web_ui._client_wipe_outcome(WINDOWS_RESET + MACOS_RESET)[0] is True
    assert web_ui._client_wipe_outcome(MACOS_RESET + WINDOWS_RESET)[0] is False


def test_an_unlogged_wipe_is_unknown_not_a_pass():
    assert web_ui._client_wipe_outcome("[CIRISApp] nothing about a reset here\n") is None


def test_the_reset_step_raises_on_an_unfinished_wipe():
    source = inspect.getsource(web_ui.DesktopAppTestRunner.test_reset_device_flow)
    check = source[source.index("_client_wipe_outcome(") :]
    assert "if not wiped:" in check and "raise RuntimeError" in check


# ─── 2. a fresh bring-up wipes the whole home ───────────────────────────────


def _fake_repo(monkeypatch, tmp_path: Path) -> Path:
    """Point the module's repo root at a scratch dir, so the test never touches <repo>/data."""
    repo = tmp_path / "repo"
    fake_file = repo / "tools" / "qa_runner" / "modules" / "web_ui" / "__main__.py"
    fake_file.parent.mkdir(parents=True)
    monkeypatch.setattr(web_ui, "__file__", str(fake_file))
    return repo


def _seeded_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / "identity").mkdir(parents=True)
    (home / "identity" / "ed25519.seed").write_bytes(b"kept-classical-half")
    (home / "identity" / "ml_dsa_65.seed").write_bytes(b"pqc-half")
    (home / "data" / "edge").mkdir(parents=True)
    (home / "data" / "edge" / "edge_identity.rid.transit-kex").write_bytes(b"transport")
    monkeypatch.setenv("CIRIS_HOME", str(home))
    return home


def test_the_wipe_removes_identity_with_data(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path)
    home = _seeded_home(monkeypatch, tmp_path)
    web_ui._wipe_dev_data()
    assert not (home / "identity").exists(), "kept seeds with a wiped data/edge give one key two transport identities"
    assert (home / "data").is_dir() and not any((home / "data").iterdir())


def test_a_wipe_that_leaves_anything_behind_raises(monkeypatch, tmp_path):
    _fake_repo(monkeypatch, tmp_path)
    home = _seeded_home(monkeypatch, tmp_path)
    monkeypatch.setattr(web_ui.shutil, "rmtree", lambda *a, **k: None)  # a file lock: nothing goes
    with pytest.raises(web_ui.HomeWipeIncomplete, match="identity"):
        web_ui._wipe_dev_data()
    assert (home / "identity" / "ed25519.seed").exists()


def test_both_fresh_bring_ups_stop_on_an_incomplete_wipe():
    for fn in (web_ui.run_desktop_up, web_ui.run_desktop_first_run_up):
        source = inspect.getsource(fn)
        assert "except HomeWipeIncomplete" in source and "return 1" in source


# ─── 3. nothing can start a node between the reset and the next bring-up ────


def test_the_reset_stops_the_restarted_app_and_then_its_nodes():
    source = inspect.getsource(web_ui.DesktopAppTestRunner.test_reset_device_flow)
    stop = source[source.index("async def stop_restarted_app") :]
    app_kill = stop.index("desktop_process_pattern()")
    node_kill = stop.index('"ciris-server"')
    assert app_kill < node_kill, "the app relaunches nodes, so it goes first"
    assert 'run_test("stop_restarted_app"' in source


# ─── 4. the logout waits for the shell to settle ────────────────────────────


class _ComposingApp(shell_nav_tests._CirclesApp):
    """The circles app, but its tree stays empty until it has composed after sign-in."""

    def __init__(self) -> None:
        super().__init__(rail=True)
        self.composed = False

    def on_screen(self):  # type: ignore[override]
        return super().on_screen() if self.composed else set()


def _composing_runner(app: _ComposingApp, compose_after_passes: int):
    """A runner whose app finishes composing after `compose_after_passes` missed logout passes."""
    runner = shell_nav_tests._runner(app)
    missed = {"n": 0}
    log = runner._log

    def _log(msg: str) -> None:
        if msg.startswith("no logout route yet"):
            missed["n"] += 1
            if missed["n"] >= compose_after_passes:
                app.composed = True
        log(msg)

    runner._log = _log  # type: ignore[method-assign]
    return runner


@pytest.fixture
def _fast(monkeypatch):
    for mod in (shell_nav_tests.shell_nav,):
        monkeypatch.setattr(mod, "SETTLE_S", 0.0)
        monkeypatch.setattr(mod, "POLL_S", 0.0)
        monkeypatch.setattr(mod, "HOP_TIMEOUT_S", 0.0)
    monkeypatch.setattr(web_ui, "LOGOUT_RETRY_S", 0.0)

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(web_ui.asyncio, "sleep", _no_sleep)


@pytest.mark.asyncio
async def test_logout_retries_until_the_shell_has_composed(_fast, monkeypatch):
    monkeypatch.setattr(web_ui, "LOGOUT_SETTLE_S", 30.0)
    app = _ComposingApp()
    await _composing_runner(app, compose_after_passes=2)._logout()
    assert app.page == ("screen", "Login")


@pytest.mark.asyncio
async def test_logout_still_fails_when_no_route_ever_appears(_fast, monkeypatch):
    monkeypatch.setattr(web_ui, "LOGOUT_SETTLE_S", 0.0)
    app = _ComposingApp()
    with pytest.raises(RuntimeError, match="no logout route on this install after 1 passes"):
        await _composing_runner(app, compose_after_passes=10_000)._logout()
