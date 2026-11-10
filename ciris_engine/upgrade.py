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
        (run_dir(home) / _RUNNING_FILE).write_text(json.dumps({"pid": os.getpid(), "argv": argv}), encoding="utf-8")
    except OSError as e:
        logger.warning("could not record the running process: %s", e)


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


def _requirement(version: Optional[str]) -> str:
    return f"ciris-agent=={version}" if version else "ciris-agent"


def _start_helper(home: Path, requirement: str, relaunch: Optional[List[str]]) -> Path:
    """Copy the helper out of the install and start it detached. Returns its log."""
    logs = home / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / "upgrade.log"
    helper = Path(tempfile.mkdtemp(prefix="ciris-upgrade-")) / "helper.py"
    shutil.copyfile(Path(__file__).with_name("_upgrade_helper.py"), helper)
    cmd = [
        sys.executable,
        "-I",
        str(helper),
        "--python",
        sys.executable,
        "--requirement",
        requirement,
        "--wait-pid",
        str(os.getpid()),
        "--log",
        str(log),
        "--stop-flag",
        str(stop_flag(home)),
    ]
    if relaunch:
        cmd += ["--relaunch", json.dumps(relaunch)]
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

    running = read_running(home)
    relaunch: Optional[List[str]] = None
    if running:
        pid = int(str(running["pid"]))
        print(f"Closing CIRIS (pid {pid})...")
        run_dir(home).mkdir(parents=True, exist_ok=True)
        stop_flag(home).touch()
        if not _wait_gone(pid, STOP_DEADLINE_SECS + 5.0):
            print("CIRIS didn't close in time; ending it.", file=sys.stderr)
            _end_process_tree(pid, 5.0)
        saved = running.get("argv")
        if isinstance(saved, list) and not args.no_restart:
            relaunch = [str(a) for a in saved]

    log = _start_helper(home, _requirement(args.to), relaunch)
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
