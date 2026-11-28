"""Upgrading CIRIS while it runs.

On Windows a running process locks its own files. ``pip install -U`` over a
running CIRIS replaces the client and the server, then fails on the launcher or
the desktop JAR (WinError 32), leaving a half-installed agent that dies at import
before it can log anything. Windows runner, Python 3.14, 2.18.0 -> 2.19.1:
runs 41848318081 and 41850556394. Elsewhere pip succeeds, but a running process
then lazily imports new code against old code. So in every case:

- ``ciris-agent upgrade`` (run_upgrade) is the supported path. It stops CIRIS, and
  a helper running from outside the install does the pip (_upgrade_helper.py).
- start_watch is the safety net for someone typing ``pip install -U``. It sees
  pip's first rename (``~iris_*``) and stops this process. Best effort: pip gives
  no warning, though it replaces the client and server before it reaches the agent,
  which is the window this has.

The helpers in ``ciris_server.upgrade`` (>= 0.5.245) are used when the wheel has
them; the import is guarded so an older wheel still works.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

#: Set to 0 to leave the watcher off.
WATCH_ENV = "CIRIS_UPGRADE_WATCH"
#: Seconds a stop gets before the process is ended anyway. The node's crash tests
#: show a kill loses only unacknowledged work.
STOP_DEADLINE_SECS = 15.0
_TILDE_GLOB = "~iris*"
_STOP_FLAG = "stop_for_upgrade"
_RUNNING_FILE = "ciris-agent.json"
#: The systemd --user unit the Linux per-user installer runs CIRIS as (agreed with
#: ciris-server 2026-11-27). Override for another unit name.
SYSTEMD_UNIT_ENV = "CIRIS_SYSTEMD_UNIT"
DEFAULT_SYSTEMD_UNIT = "ciris.service"


def run_dir(home: Path) -> Path:
    return home / "run"


def stop_flag(home: Path) -> Path:
    return run_dir(home) / _STOP_FLAG


def site_packages() -> Path:
    """The directory this install lives in."""
    return Path(__file__).resolve().parent.parent


def register_running(home: Path, argv: List[str]) -> None:
    """Record this launcher so ``ciris-agent upgrade`` can find it. Never raises."""
    try:
        run_dir(home).mkdir(parents=True, exist_ok=True)
        stop_flag(home).unlink(missing_ok=True)  # Left by an upgrade that didn't finish.
        state: Dict[str, object] = {"pid": os.getpid(), "argv": argv}
        unit = _supervising_unit()
        if unit:
            state["systemd_unit"] = unit
        (run_dir(home) / _RUNNING_FILE).write_text(json.dumps(state), encoding="utf-8")
    except OSError as e:
        logger.warning("could not record the running process: %s", e)


def _supervising_unit() -> Optional[str]:
    """The systemd --user unit running this process, if systemd started it.

    systemd sets INVOCATION_ID for every unit it starts. The unit name is not in
    the environment, so it is the installer's (CIRIS_SYSTEMD_UNIT, default
    ciris.service); run_upgrade checks it against the unit's MainPID before
    trusting it.
    """
    if not sys.platform.startswith("linux") or not os.environ.get("INVOCATION_ID"):
        return None
    return os.environ.get(SYSTEMD_UNIT_ENV) or DEFAULT_SYSTEMD_UNIT


def _unit_main_pid(unit: str) -> Optional[int]:
    try:
        out = subprocess.run(
            ["systemctl", "--user", "show", "-p", "MainPID", "--value", unit],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()  # fmt: skip
        return int(out) if out.isdigit() and int(out) > 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def supervised_unit(running: Dict[str, object]) -> Optional[str]:
    """The user unit that supervises the recorded process, only if systemd agrees."""
    unit = running.get("systemd_unit")
    if not isinstance(unit, str) or not unit or shutil.which("systemctl") is None or shutil.which("systemd-run") is None:
        return None
    return unit if _unit_main_pid(unit) == running.get("pid") else None


def read_running(home: Path) -> Optional[Dict[str, object]]:
    """The recorded launcher, if it's still alive."""
    try:
        state = json.loads((run_dir(home) / _RUNNING_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pid = state.get("pid") if isinstance(state, dict) else None
    return state if isinstance(pid, int) and psutil.pid_exists(pid) else None


def upgrade_reason(site: Path, home: Path, baseline: Dict[str, str]) -> Optional[str]:
    """Why this process should stop for an upgrade, or None."""
    if stop_flag(home).exists():
        return "ciris-agent upgrade asked CIRIS to stop"
    try:
        from ciris_server.upgrade import upgrade_started  # type: ignore[import-not-found, import-untyped, unused-ignore]

        found = upgrade_started(site, baseline)
        return str(found) if found else None
    except ImportError:
        tilde = sorted(p.name for p in site.glob(_TILDE_GLOB))
        return f"pip is replacing {', '.join(tilde)}" if tilde else None


def _dist_versions(site: Path) -> Dict[str, str]:
    try:
        from ciris_server.upgrade import dist_versions  # type: ignore[import-not-found, import-untyped, unused-ignore]

        return dict(dist_versions(site))
    except ImportError:
        return {}


def start_watch(
    on_upgrade: Callable[[str], None], home: Path, site: Optional[Path] = None, interval_secs: float = 1.0
) -> Optional[threading.Event]:
    """Call ``on_upgrade(reason)`` once when an upgrade starts. Returns None when off."""
    if os.environ.get(WATCH_ENV, "1").strip() == "0":
        return None
    where = site or site_packages()
    if not where.is_dir():
        return None
    baseline = _dist_versions(where)
    finished = threading.Event()

    def run() -> None:
        while not finished.wait(interval_secs):
            reason = upgrade_reason(where, home, baseline)
            if reason:
                on_upgrade(reason)
                return

    threading.Thread(target=run, name="ciris-upgrade-watch", daemon=True).start()
    return finished


def stop_this_process(reason: str) -> None:
    """Stop the server in this process for an upgrade, and exit inside the deadline."""
    print(f"\nCIRIS is closing for an upgrade: {reason}. Start it again when the upgrade finishes.", file=sys.stderr)
    logger.warning("stopping for an upgrade: %s", reason)
    timer = threading.Timer(STOP_DEADLINE_SECS, os._exit, args=(0,))
    timer.daemon = True
    timer.start()
    from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

    request_global_shutdown(f"Upgrade: {reason}")


def _end_process_tree(pid: int, deadline_secs: float) -> None:
    """End `pid` and its children, waiting for them to stop."""
    try:
        root = psutil.Process(pid)
        tree = [*root.children(recursive=True), root]
    except psutil.NoSuchProcess:
        return
    for proc in tree:
        try:
            proc.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(tree, timeout=deadline_secs)
    for proc in alive:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass


def console_python(executable: Optional[str] = None) -> str:
    """The console Python beside ``executable``: ``pythonw.exe`` prints nowhere.

    The Windows hand-off can leave CIRIS running under pythonw; an upgrade typed
    or started from it would run with no visible output.
    """
    exe = Path(executable or sys.executable)
    if exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def upgrade_argv(executable: Optional[str] = None) -> List[str]:
    """Argv that upgrades THIS install: its own Python, never whatever is first on PATH."""
    return [console_python(executable), "-m", "ciris_engine.cli", "upgrade"]


def upgrade_command(executable: Optional[str] = None, platform: Optional[str] = None) -> str:
    """``upgrade_argv`` as text for the platform's usual shell (PowerShell on Windows)."""
    argv = upgrade_argv(executable)
    if (platform or sys.platform) == "win32":
        return f'& "{argv[0]}" ' + " ".join(argv[1:])
    import shlex

    return shlex.join(argv)


def release_version(version: str) -> Optional[str]:
    """``version`` rebuilt from its integers (2.24.0), or None if it is not a release number.

    The helper does the same; only digits and dots ever reach pip's command line.
    """
    parts = version.split(".")
    if not 1 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
        return None
    return ".".join(str(int(p)) for p in parts)


def _start_helper(
    home: Path,
    version: Optional[str],
    relaunch: Optional[List[str]],
    wait_pid: Optional[int] = None,
    outside_unit: Optional[str] = None,
) -> Path:
    """Copy the helper out of the install and start it detached. Returns its log.

    With ``outside_unit``, the helper runs in its own transient user unit
    (systemd-run): stopping a unit ends every process in it, including this
    command when the app's Upgrade button started it from inside the unit.
    """
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / "upgrade.log"
    helper = Path(tempfile.mkdtemp(prefix="ciris-upgrade-")) / "helper.py"
    shutil.copyfile(Path(__file__).with_name("_upgrade_helper.py"), helper)
    # The helper installs into the interpreter that runs it, so it is started by this one.
    cmd = [sys.executable, "-I", str(helper)]
    if version:
        cmd += ["--version", version]
    cmd += [
        "--wait-pid",
        str(wait_pid or os.getpid()),
        "--log",
        str(log),
        "--stop-flag",
        str(stop_flag(home)),
    ]
    if relaunch:
        cmd += ["--relaunch", json.dumps(relaunch)]
    if outside_unit:
        stem = outside_unit.removesuffix(".service")
        cmd = ["systemd-run", "--user", "--collect", "--quiet", f"--unit={stem}-upgrade-{os.getpid()}", "--", *cmd]
    kwargs: Dict[str, object] = {"start_new_session": True}
    if sys.platform == "win32":
        kwargs = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kwargs)  # type: ignore[call-overload]
    return log


def run_upgrade(argv: List[str], home: Optional[Path] = None) -> int:
    """``ciris-agent upgrade``: stop CIRIS, then let the helper run pip."""
    ap = argparse.ArgumentParser(prog="ciris-agent upgrade", description="Upgrade CIRIS, closing it first if it's running.")
    ap.add_argument("--to", metavar="VERSION", help="version to install (default: the latest)")
    ap.add_argument("--no-restart", action="store_true", help="don't start CIRIS again afterwards")
    args = ap.parse_args(argv)
    if home is None:
        from ciris_engine.logic.utils.path_resolution import get_ciris_home

        home = get_ciris_home()

    version = release_version(args.to) if args.to is not None else None
    if args.to is not None and version is None:
        print(f"--to must be a release such as 2.24.0, got {args.to!r}", file=sys.stderr)
        return 2
    running = read_running(home)
    unit = supervised_unit(running) if running else None
    if running and unit:
        return _upgrade_under_systemd(home, running, unit, version, args.no_restart)
    relaunch = _close_running(home, running, args.no_restart) if running else None
    return _hand_to_helper(home, version, relaunch)


def _upgrade_under_systemd(
    home: Path, running: Dict[str, object], unit: str, version: Optional[str], no_restart: bool
) -> int:
    """systemd owns this process: it stops and starts it, or Restart= and the helper's relaunch would race pip."""
    pid = int(str(running["pid"]))
    relaunch = None if no_restart else ["systemctl", "--user", "start", unit]
    try:
        log = _start_helper(home, version, relaunch, wait_pid=pid, outside_unit=unit)
    except OSError as e:
        print(f"Could not start the upgrade helper: {e}", file=sys.stderr)
        return 1
    print(f"Stopping {unit} (pid {pid}) for the upgrade. Progress: {log}")
    subprocess.run(["systemctl", "--user", "stop", "--no-block", unit], check=False)
    if relaunch:
        print(f"{unit} starts again when the upgrade finishes.")
    return 0


def _close_running(home: Path, running: Dict[str, object], no_restart: bool) -> Optional[List[str]]:
    """Ask the running CIRIS to stop (ending it if it won't). Returns the argv to start it again, if any."""
    pid = int(str(running["pid"]))
    print(f"Closing CIRIS (pid {pid})...")
    run_dir(home).mkdir(parents=True, exist_ok=True)
    stop_flag(home).touch()
    if not _wait_gone(pid, STOP_DEADLINE_SECS + 5.0):
        print("CIRIS didn't close in time; ending it.", file=sys.stderr)
        _end_process_tree(pid, 5.0)
    saved = running.get("argv")
    if isinstance(saved, list) and not no_restart:
        return [str(a) for a in saved]
    return None


def _hand_to_helper(home: Path, version: Optional[str], relaunch: Optional[List[str]]) -> int:
    try:
        log = _start_helper(home, version, relaunch)
    except OSError as e:
        print(f"Could not start the upgrade helper: {e}. CIRIS was closed; start it again.", file=sys.stderr)
        return 1
    print(f"Upgrading. Progress: {log}")
    if relaunch:
        print("CIRIS starts again when the upgrade finishes.")
    return 0


def _wait_gone(pid: int, timeout_secs: float) -> bool:
    end = time.monotonic() + timeout_secs
    while time.monotonic() < end:
        if not psutil.pid_exists(pid):
            return True
        time.sleep(0.25)
    return not psutil.pid_exists(pid)
