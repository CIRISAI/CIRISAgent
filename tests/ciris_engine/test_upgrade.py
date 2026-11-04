"""Upgrading while CIRIS runs (Windows: WinError 32, runs 41848318081 and 41850556394)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine import cli, desktop_launcher, upgrade


@pytest.mark.parametrize(
    "given, expected",
    [
        (["--server"], ["--adapter", "api"]),
        (["--headless", "--port", "9000"], ["--adapter", "api", "--port", "9000"]),
        (["--server", "--adapter", "discord"], ["--adapter", "discord"]),
        (["--adapter", "api"], ["--adapter", "api"]),
    ],
)
def test_server_flags_become_what_main_accepts(monkeypatch: pytest.MonkeyPatch, given: list, expected: list) -> None:
    monkeypatch.setattr(sys, "argv", ["ciris-agent", *given])
    cli._normalize_server_flags()
    assert sys.argv[1:] == expected


def test_the_newest_jar_wins_whatever_the_listing_order() -> None:
    old, new = Path("CIRIS-windows-x64-1.5.99.jar"), Path("CIRIS-windows-x64-1.5.237.jar")
    assert desktop_launcher._newest_jar([old, new]) == new
    assert desktop_launcher._newest_jar([new, old]) == new


def test_a_tilde_directory_means_an_upgrade_started(tmp_path: Path) -> None:
    home, site = tmp_path / "home", tmp_path / "site"
    site.mkdir()
    assert upgrade.upgrade_reason(site, home, {}) is None
    (site / "~iris_client").mkdir()
    assert "~iris_client" in (upgrade.upgrade_reason(site, home, {}) or "")


def test_the_stop_flag_means_an_upgrade_started(tmp_path: Path) -> None:
    home, site = tmp_path / "home", tmp_path / "site"
    site.mkdir()
    upgrade.run_dir(home).mkdir(parents=True)
    upgrade.stop_flag(home).touch()
    assert "ciris-agent upgrade" in (upgrade.upgrade_reason(site, home, {}) or "")


def test_the_watch_fires_once_and_can_be_turned_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home, site = tmp_path / "home", tmp_path / "site"
    site.mkdir()
    fired: list = []
    done = threading.Event()

    def on_upgrade(reason: str) -> None:
        fired.append(reason)
        done.set()

    stop = upgrade.start_watch(on_upgrade, home, site, interval_secs=0.01)
    assert stop is not None
    (site / "~iris_server").mkdir()
    assert done.wait(5)
    assert len(fired) == 1
    monkeypatch.setenv(upgrade.WATCH_ENV, "0")
    assert upgrade.start_watch(on_upgrade, home, site) is None


def test_registering_clears_a_stale_flag_and_read_back(tmp_path: Path) -> None:
    upgrade.run_dir(tmp_path).mkdir()
    upgrade.stop_flag(tmp_path).touch()
    upgrade.register_running(tmp_path, ["python", "-m", "ciris_engine.cli"])
    assert not upgrade.stop_flag(tmp_path).exists()
    state = upgrade.read_running(tmp_path)
    assert state and state["pid"] == os.getpid()


def test_a_dead_recorded_process_is_not_running(tmp_path: Path) -> None:
    upgrade.run_dir(tmp_path).mkdir()
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    (upgrade.run_dir(tmp_path) / "ciris-agent.json").write_text(json.dumps({"pid": proc.pid, "argv": []}))
    assert upgrade.read_running(tmp_path) is None


def test_upgrade_with_nothing_running_hands_straight_to_the_helper(tmp_path: Path) -> None:
    with patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper:
        assert upgrade.run_upgrade(["--to", "2.19.3"], home=tmp_path) == 0
    helper.assert_called_once_with(tmp_path, "ciris-agent==2.19.3", None)


def test_upgrade_stops_the_running_process_and_restarts_it(tmp_path: Path) -> None:
    upgrade.register_running(tmp_path, ["python", "-m", "ciris_engine.cli"])
    with (
        patch.object(upgrade, "_wait_gone", return_value=True),
        patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper,
    ):
        assert upgrade.run_upgrade([], home=tmp_path) == 0
    assert upgrade.stop_flag(tmp_path).exists(), "the running process is asked first"
    helper.assert_called_once_with(tmp_path, "ciris-agent", ["python", "-m", "ciris_engine.cli"])


def test_no_restart_is_honoured(tmp_path: Path) -> None:
    upgrade.register_running(tmp_path, ["x"])
    with (
        patch.object(upgrade, "_wait_gone", return_value=True),
        patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper,
    ):
        upgrade.run_upgrade(["--no-restart"], home=tmp_path)
    assert helper.call_args.args[2] is None


def test_a_process_that_wont_close_is_ended(tmp_path: Path) -> None:
    upgrade.register_running(tmp_path, ["x"])
    with (
        patch.object(upgrade, "_wait_gone", return_value=False),
        patch.object(upgrade, "_end_process_tree") as end,
        patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log"),
    ):
        upgrade.run_upgrade([], home=tmp_path)
    end.assert_called_once()


def test_the_helper_imports_nothing_of_ours() -> None:
    """It runs outside the install it replaces: a package import would lock or fail."""
    source = Path(upgrade.__file__).with_name("_upgrade_helper.py").read_text(encoding="utf-8")
    assert "ciris_engine" not in "".join(l for l in source.splitlines() if l.startswith(("import ", "from ")))
    result = subprocess.run(
        [sys.executable, "-I", str(Path(upgrade.__file__).with_name("_upgrade_helper.py")), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_the_windows_launcher_hands_off_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    # pip's launcher strips ".exe" from argv[0]; __main__ still names the exe.
    monkeypatch.setattr(sys, "argv", [r"C:\\py\\Scripts\\ciris-agent", "--adapter", "api"])
    monkeypatch.setattr(sys.modules["__main__"], "__file__", r"C:\\py\\Scripts\\ciris-agent.exe\\__main__.py", raising=False)
    monkeypatch.delenv(cli.HANDOFF_ENV, raising=False)
    with patch("ciris_engine.cli.subprocess.Popen") as popen:
        with pytest.raises(SystemExit) as done:
            cli._hand_off_from_launcher()
    assert done.value.code == 0
    command = popen.call_args.args[0]
    assert command[1:] == ["-m", "ciris_engine.cli", "--adapter", "api"]
    assert popen.call_args.kwargs["env"][cli.HANDOFF_ENV] == "0", "the child must not hand off again"


@pytest.mark.parametrize(
    "platform, argv0, env, extra",
    [
        ("linux", "/usr/bin/ciris-agent", None, []),
        ("win32", r"C:\\py\\Lib\\site-packages\\ciris_engine\\cli.py", None, []),
        ("win32", r"C:\\py\\Scripts\\ciris-agent.exe", "0", []),
        ("win32", r"C:\\py\\Scripts\\ciris-agent.exe", None, ["--help"]),
    ],
)
def test_the_launcher_stays_when_it_should(
    monkeypatch: pytest.MonkeyPatch, platform: str, argv0: str, env: str, extra: list
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "argv", ["ciris-agent", *extra])
    monkeypatch.setattr(sys.modules["__main__"], "__file__", argv0, raising=False)
    if env is None:
        monkeypatch.delenv(cli.HANDOFF_ENV, raising=False)
    else:
        monkeypatch.setenv(cli.HANDOFF_ENV, env)
    with patch("ciris_engine.cli.subprocess.Popen") as popen:
        cli._hand_off_from_launcher()
    popen.assert_not_called()


def test_the_jar_runs_from_a_copy_outside_the_install(tmp_path: Path) -> None:
    jar = tmp_path / "site" / "CIRIS-windows-x64-1.5.237.jar"
    jar.parent.mkdir()
    jar.write_bytes(b"jar")
    home = tmp_path / "home"
    with patch("ciris_engine.logic.utils.path_resolution.get_ciris_home", return_value=home):
        copy = desktop_launcher._run_from_private_copy(jar)
    assert copy.read_bytes() == b"jar"
    assert home in copy.parents and jar.parent not in copy.parents
