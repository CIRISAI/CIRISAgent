"""Upgrading while CIRIS runs (Windows: WinError 32, runs 41848318081 and 41850556394)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import List, Optional
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
    helper.assert_called_once_with(tmp_path, "2.19.3", None)


def test_upgrade_stops_the_running_process_and_restarts_it(tmp_path: Path) -> None:
    upgrade.register_running(tmp_path, ["python", "-m", "ciris_engine.cli"])
    with (
        patch.object(upgrade, "_wait_gone", return_value=True),
        patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper,
    ):
        assert upgrade.run_upgrade([], home=tmp_path) == 0
    assert upgrade.stop_flag(tmp_path).exists(), "the running process is asked first"
    helper.assert_called_once_with(tmp_path, None, ["python", "-m", "ciris_engine.cli"])


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


# --- the upgrade command names THIS interpreter (2026-11-27: two Pythons, one stale) ---


def test_upgrade_argv_is_this_python_not_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "executable", "/opt/py314/bin/python3")
    assert upgrade.upgrade_argv() == ["/opt/py314/bin/python3", "-m", "ciris_engine.cli", "upgrade"]


def test_the_upgrade_module_path_really_runs_the_upgrade_verb() -> None:
    # `python -m ciris_engine.cli upgrade` only works while cli.py keeps its __main__ guard.
    assert 'if __name__ == "__main__":' in Path(cli.__file__).read_text(encoding="utf-8")


def test_pythonw_is_swapped_for_the_console_python(tmp_path: Path) -> None:
    (tmp_path / "python.exe").write_text("")
    assert upgrade.console_python(str(tmp_path / "pythonw.exe")) == str(tmp_path / "python.exe")
    # No console Python beside it: keep what we were given rather than invent a path.
    assert upgrade.console_python(str(tmp_path / "sub" / "pythonw.exe")) == str(tmp_path / "sub" / "pythonw.exe")


def test_the_windows_command_is_powershell_runnable() -> None:
    exe = r"C:\Users\franc\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    assert upgrade.upgrade_command(exe, platform="win32") == f'& "{exe}" -m ciris_engine.cli upgrade'


def test_the_posix_command_quotes_a_path_with_spaces() -> None:
    assert upgrade.upgrade_command("/opt/my py/python3", platform="linux") == "'/opt/my py/python3' -m ciris_engine.cli upgrade"


def test_the_helper_uses_pip_where_there_is_pip(tmp_path: Path) -> None:
    from ciris_engine import _upgrade_helper as helper

    log = str(tmp_path / "u.log")
    argv = helper.pip_install_argv(None, log)
    assert argv == [sys.executable, "-m", "pip", "install", "--upgrade", "ciris-agent"]


def test_the_helper_falls_back_to_uv_without_pip(tmp_path: Path) -> None:
    from ciris_engine import _upgrade_helper as helper

    log = str(tmp_path / "u.log")
    with patch.object(helper.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), patch.object(
        helper.shutil, "which", return_value="/usr/bin/uv"
    ):
        argv = helper.pip_install_argv("2.24.0", log)
    assert argv == ["/usr/bin/uv", "pip", "install", "--python", sys.executable, "--upgrade", "ciris-agent==2.24.0"]
    assert "using uv" in Path(log).read_text(encoding="utf-8")


def test_the_helper_installs_into_its_own_interpreter() -> None:
    """No interpreter path is taken from the command line: the helper runs as the Python it upgrades."""
    from ciris_engine import _upgrade_helper as helper

    source = Path(helper.__file__).read_text(encoding="utf-8")
    assert "--python\"" not in source.split("def main()")[1]


@pytest.mark.parametrize(
    "version",
    ["2.24.0 --index-url http://evil", "2.24.0; echo", "requests", "2.24.0rc1", "v2.24.0", "", "1.2.3.4.5"],
)
def test_the_helper_installs_only_a_release_of_ciris_agent(version: str) -> None:
    from ciris_engine import _upgrade_helper as helper

    with pytest.raises(SystemExit):
        helper.requirement_for(version)


def test_a_release_version_is_rebuilt_from_its_digits() -> None:
    from ciris_engine import _upgrade_helper as helper

    assert helper.requirement_for("2.24.0") == "ciris-agent==2.24.0"
    assert helper.requirement_for("02.24.00") == "ciris-agent==2.24.0"
    assert helper.requirement_for(None) == "ciris-agent"


def test_logging_setup_states_the_install(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from ciris_engine.logic.utils import logging_config

    with caplog.at_level(logging.INFO):
        logging_config._log_install_line()
    line = next(r.getMessage() for r in caplog.records if "[INSTALL]" in r.getMessage())
    assert sys.version.split()[0] in line
    assert "ciris_engine.cli upgrade" in line


# --- desktop UI heartbeat (CIRISClient PLAN-0.5.244 §2.7) ---


class _FakeProc:
    def __init__(self, pid: int, alive_polls: int) -> None:
        self.pid, self._left = pid, alive_polls

    def poll(self) -> Optional[int]:
        self._left -= 1
        return None if self._left >= 0 else 0


def test_heartbeat_path_follows_the_clients_home_rule(tmp_path: Path) -> None:
    assert desktop_launcher.ui_heartbeat_path({"CIRIS_HOME": str(tmp_path)}) == tmp_path / "run" / "desktop_ui.heartbeat"
    assert desktop_launcher.ui_heartbeat_path({}) == Path.home() / "ciris" / "run" / "desktop_ui.heartbeat"


def test_heartbeat_age_ignores_missing_malformed_and_foreign_lines(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    assert desktop_launcher.ui_heartbeat_age(hb, 42, 100.0) is None  # older client: no file
    hb.write_text("garbage")
    assert desktop_launcher.ui_heartbeat_age(hb, 42, 100.0) is None
    hb.write_text("90000 7")  # a previous window's leftover
    assert desktop_launcher.ui_heartbeat_age(hb, 42, 100.0) is None
    hb.write_text("90000 42")
    assert desktop_launcher.ui_heartbeat_age(hb, 42, 100.0) == pytest.approx(10.0)


def test_a_stale_window_is_reported_once_then_its_recovery(tmp_path: Path) -> None:
    hb = tmp_path / "hb"
    hb.write_text("0 42")  # last beat at t=0
    times = iter([10.0, 40.0, 50.0, 60.0])
    reports: List[str] = []

    def _sleep(_s: float) -> None:
        # The window recovers after the third check.
        if len(reports) == 1 and next_t[0] >= 50.0:
            hb.write_text("59000 42")

    next_t = [0.0]

    def _clock() -> float:
        next_t[0] = next(times)
        return next_t[0]

    desktop_launcher.watch_ui_heartbeat(_FakeProc(42, 4), hb, reports.append, clock=_clock, sleep=_sleep)  # type: ignore[arg-type]
    assert len(reports) == 2
    assert "has not responded for 40 s" in reports[0]
    assert "responding again" in reports[1]


def test_no_heartbeat_file_means_no_report(tmp_path: Path) -> None:
    reports: List[str] = []
    desktop_launcher.watch_ui_heartbeat(  # type: ignore[arg-type]
        _FakeProc(42, 3), tmp_path / "none", reports.append, clock=lambda: 1e9, sleep=lambda _s: None
    )
    assert reports == []


# --- the private JAR copy keeps its Class-Path (client 0.5.243: FFmpeg via ../../ciris_holon/...) ---


def _jar_with_class_path(path: Path, entries: List[str]) -> None:
    import zipfile

    # Manifest lines wrap at 72 bytes with a leading space, as the JDK writes them.
    value = "Class-Path: " + " ".join(entries)
    lines = [value[:70]] + [" " + value[i : i + 69] for i in range(70, len(value), 69)]
    manifest = "Manifest-Version: 1.0\r\n" + "\r\n".join(lines) + "\r\nMain-Class: ai.ciris.desktop.MainKt\r\n\r\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/MANIFEST.MF", manifest)


def test_class_path_entries_are_read_across_wrapped_lines(tmp_path: Path) -> None:
    entries = [
        "../../ciris_holon/media/jars/javacpp-1.5.11-linux-x86_64.jar",
        "../../ciris_holon/media/jars/ffmpeg-7.1-1.5.11-linux-x86_64.jar",
    ]
    jar = tmp_path / "CIRIS.jar"
    _jar_with_class_path(jar, entries)
    assert desktop_launcher.manifest_class_path(jar) == entries


def test_the_private_copy_brings_its_class_path_along(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed = site / "ciris_engine" / "desktop_app" / "CIRIS-linux-x64-1.5.243.jar"
    entry = "../../ciris_holon/media/jars/ffmpeg-7.1-1.5.11-linux-x86_64.jar"
    _jar_with_class_path(installed, [entry, "../../ciris_holon/media/jars/missing.jar"])
    (site / "ciris_holon" / "media" / "jars").mkdir(parents=True)
    (site / "ciris_holon" / "media" / "jars" / "ffmpeg-7.1-1.5.11-linux-x86_64.jar").write_bytes(b"ffmpeg")

    private = tmp_path / "home" / "runtime" / "desktop" / installed.name
    private.parent.mkdir(parents=True)
    private.write_bytes(installed.read_bytes())
    with patch("ciris_engine.logic.utils.path_resolution.get_ciris_home", return_value=tmp_path / "home"):
        desktop_launcher._with_class_path(installed, private)
    # Resolved from the COPY's directory, exactly as the JVM will.
    assert (private.parent / entry).resolve().read_bytes() == b"ffmpeg"
    assert (tmp_path / "home" / "ciris_holon" / "media" / "jars" / "ffmpeg-7.1-1.5.11-linux-x86_64.jar").exists()


def test_running_in_place_copies_nothing(tmp_path: Path) -> None:
    jar = tmp_path / "CIRIS.jar"
    _jar_with_class_path(jar, ["../x.jar"])
    desktop_launcher._with_class_path(jar, jar)
    assert not (tmp_path.parent / "x.jar").exists()


def test_the_installed_client_jar_parses_if_present() -> None:
    jar = desktop_launcher.find_desktop_jar()
    if jar is None:
        pytest.skip("no desktop JAR installed here")
    for entry in desktop_launcher.manifest_class_path(jar):
        assert not entry.startswith("/")
        assert not entry.startswith("file:")


def test_class_path_copies_never_leave_ciris_home(tmp_path: Path) -> None:
    site = tmp_path / "site"
    installed = site / "a" / "b" / "c" / "d" / "CIRIS.jar"
    escape = "../../../outside.jar"  # source: site/a/outside.jar; target: tmp_path/outside.jar
    _jar_with_class_path(installed, [escape])
    (site / "a").mkdir(parents=True, exist_ok=True)
    (site / "a" / "outside.jar").write_bytes(b"x")
    private = tmp_path / "home" / "runtime" / "desktop" / "CIRIS.jar"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"jar")
    with patch("ciris_engine.logic.utils.path_resolution.get_ciris_home", return_value=tmp_path / "home"):
        desktop_launcher._with_class_path(installed, private)
    assert (private.parent / escape).resolve() == (tmp_path / "outside.jar").resolve()
    assert not (tmp_path / "outside.jar").exists()


def test_a_current_class_path_copy_is_not_rewritten(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed = site / "ciris_engine" / "desktop_app" / "CIRIS.jar"
    entry = "../../ciris_holon/media/jars/ffmpeg.jar"
    _jar_with_class_path(installed, [entry])
    (site / "ciris_holon" / "media" / "jars").mkdir(parents=True)
    (site / "ciris_holon" / "media" / "jars" / "ffmpeg.jar").write_bytes(b"ffmpeg")
    private = tmp_path / "home" / "runtime" / "desktop" / "CIRIS.jar"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"jar")
    with patch("ciris_engine.logic.utils.path_resolution.get_ciris_home", return_value=tmp_path / "home"):
        desktop_launcher._with_class_path(installed, private)
        copied = (private.parent / entry).resolve()
        before = copied.stat().st_mtime_ns
        with patch.object(desktop_launcher.shutil, "copyfile", side_effect=AssertionError("rewrote a current file")):
            desktop_launcher._with_class_path(installed, private)
    assert copied.stat().st_mtime_ns == before


def test_the_jars_sha256sums_travels_with_them(tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    installed = site / "ciris_engine" / "desktop_app" / "CIRIS.jar"
    entry = "../../ciris_holon/media/jars/ffmpeg.jar"
    _jar_with_class_path(installed, [entry])
    jars = site / "ciris_holon" / "media" / "jars"
    jars.mkdir(parents=True)
    (jars / "ffmpeg.jar").write_bytes(b"ffmpeg")
    (jars / "SHA256SUMS").write_text("aaaa  ffmpeg.jar\n")
    private = tmp_path / "home" / "runtime" / "desktop" / "CIRIS.jar"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"jar")
    copied = (private.parent / entry).resolve().parent / "SHA256SUMS"
    with patch("ciris_engine.logic.utils.path_resolution.get_ciris_home", return_value=tmp_path / "home"):
        desktop_launcher._with_class_path(installed, private)
        assert copied.read_text() == "aaaa  ffmpeg.jar\n"
        (jars / "SHA256SUMS").write_text("bbbb  ffmpeg.jar\n")  # same size, new content
        desktop_launcher._with_class_path(installed, private)
    assert copied.read_text() == "bbbb  ffmpeg.jar\n"


# --- systemd --user (ciris-server's Linux per-user installer runs CIRIS as ciris.service) ---


def test_a_systemd_started_process_records_its_unit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(upgrade.sys, "platform", "linux")
    monkeypatch.setenv("INVOCATION_ID", "abc")
    monkeypatch.delenv("CIRIS_SYSTEMD_UNIT", raising=False)
    upgrade.register_running(tmp_path, ["x"])
    state = json.loads((upgrade.run_dir(tmp_path) / "ciris-agent.json").read_text())
    assert state["systemd_unit"] == "ciris.service"


def test_without_systemd_no_unit_is_recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    upgrade.register_running(tmp_path, ["x"])
    assert "systemd_unit" not in json.loads((upgrade.run_dir(tmp_path) / "ciris-agent.json").read_text())


def _supervised(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, main_pid: int) -> None:
    monkeypatch.setattr(upgrade.sys, "platform", "linux")
    monkeypatch.setenv("INVOCATION_ID", "abc")
    upgrade.register_running(tmp_path, ["python", "-m", "ciris_engine.cli", "--adapter", "api"])
    monkeypatch.setattr(upgrade.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(upgrade, "_unit_main_pid", lambda unit: main_pid)


def test_under_systemd_the_unit_is_stopped_and_started_by_systemd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    _supervised(tmp_path, monkeypatch, main_pid=os.getpid())
    calls: list = []
    monkeypatch.setattr(upgrade.subprocess, "run", lambda argv, **kw: calls.append(argv))
    with patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper:
        assert upgrade.run_upgrade([], home=tmp_path) == 0
    # The helper waits for CIRIS's pid, restarts through systemctl, and runs outside the unit.
    args, kwargs = helper.call_args
    assert args[2] == ["systemctl", "--user", "start", "ciris.service"]
    assert kwargs == {"wait_pid": os.getpid(), "outside_unit": "ciris.service"}
    assert ["systemctl", "--user", "stop", "--no-block", "ciris.service"] in calls
    assert not upgrade.stop_flag(tmp_path).exists(), "systemd stops it; no stop flag, no kill"


def test_under_systemd_no_restart_leaves_the_unit_stopped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    _supervised(tmp_path, monkeypatch, main_pid=os.getpid())
    monkeypatch.setattr(upgrade.subprocess, "run", lambda argv, **kw: None)
    with patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper:
        upgrade.run_upgrade(["--no-restart"], home=tmp_path)
    assert helper.call_args.args[2] is None


def test_a_unit_that_does_not_run_this_pid_is_not_trusted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative: INVOCATION_ID from some other unit falls back to the ordinary stop."""
    _supervised(tmp_path, monkeypatch, main_pid=1)
    with (
        patch.object(upgrade, "_wait_gone", return_value=True),
        patch.object(upgrade, "_start_helper", return_value=tmp_path / "u.log") as helper,
    ):
        upgrade.run_upgrade([], home=tmp_path)
    assert upgrade.stop_flag(tmp_path).exists()
    assert helper.call_args.kwargs == {}


def test_the_helper_leaves_the_unit_through_systemd_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list = []
    monkeypatch.setattr(upgrade.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    upgrade._start_helper(tmp_path, None, ["systemctl", "--user", "start", "ciris.service"], wait_pid=4242, outside_unit="ciris.service")
    cmd = started[0]
    assert cmd[:4] == ["systemd-run", "--user", "--collect", "--quiet"]
    assert cmd[4].startswith("--unit=ciris-upgrade-")
    assert cmd[cmd.index("--wait-pid") + 1] == "4242"


def test_a_version_that_is_not_one_is_refused(tmp_path: Path) -> None:
    with patch.object(upgrade, "_start_helper") as helper:
        assert upgrade.run_upgrade(["--to", "2.24.0 --index-url http://evil"], home=tmp_path) == 2
    helper.assert_not_called()


def test_a_helper_that_cannot_start_is_a_failure(tmp_path: Path) -> None:
    with patch.object(upgrade, "_start_helper", side_effect=OSError("no python")):
        assert upgrade.run_upgrade([], home=tmp_path) == 1


def test_the_helper_is_started_by_this_python_with_only_a_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list = []
    monkeypatch.setattr(upgrade.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    upgrade._start_helper(tmp_path, "2.24.0", None)
    cmd = started[0]
    assert cmd[:2] == [sys.executable, "-I"]
    assert cmd[cmd.index("--version") + 1] == "2.24.0"
    assert "--python" not in cmd
    assert "--requirement" not in cmd
