"""Runs pip for ``ciris-agent upgrade``, from OUTSIDE the install it replaces.

STANDARD LIBRARY ONLY, and never imported from the package: ciris_engine.upgrade
copies this file to a temp directory and runs it with a bare interpreter, because
on Windows anything running from site-packages, or from Scripts\\ciris-agent.exe,
is a file pip can't move. pip then fails part way through (WinError 32) and leaves
a half-installed agent that dies at import.

    python -I helper.py [--version 2.24.0] --wait-pid N --log F --stop-flag F [--relaunch JSON]

It installs into the interpreter that runs it (sys.executable), and takes no path to one.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from typing import List, Optional


def wait_for_exit(pid: int, timeout_secs: float) -> bool:
    """True once `pid` has exited. Windows has no signal 0: os.kill would END it."""
    if sys.platform == "win32":
        import ctypes

        synchronize = 0x00100000
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return True
        try:
            return kernel32.WaitForSingleObject(handle, int(timeout_secs * 1000)) == 0
        finally:
            kernel32.CloseHandle(handle)
    end = time.monotonic() + timeout_secs
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.2)
    return False


def run(cmd: List[str], log: str) -> int:
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"\n$ {' '.join(cmd)}\n")
        out.flush()
        return subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, check=False).returncode


def say(log: str, text: str) -> None:
    with open(log, "a", encoding="utf-8") as out:
        out.write(f"[upgrade {time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")


def normalized_version(version: str) -> str:
    """``version`` rebuilt from its integers (2.24.0), else SystemExit.

    Releases are numeric. Rebuilding from int() means no text a caller supplied
    reaches pip's command line, only digits and dots.
    """
    parts = version.split(".")
    if not 1 <= len(parts) <= 4 or not all(p.isdigit() for p in parts):
        raise SystemExit(f"--version must be a release such as 2.24.0, got {version!r}")
    return ".".join(str(int(p)) for p in parts)


def requirement_for(version: Optional[str]) -> str:
    """The one package this helper installs: ciris-agent, optionally pinned."""
    return "ciris-agent" if version is None else f"ciris-agent=={normalized_version(version)}"


def pip_install_argv(version: Optional[str], log: str) -> List[str]:
    """The install command for THIS interpreter's environment.

    The helper is started by the interpreter it upgrades (``python -I helper.py``),
    so it installs into ``sys.executable`` and takes no interpreter path from its
    arguments. ``python -m pip`` where that environment has pip (pip, pipx); a
    ``uv tool`` environment has none, so there it is ``uv pip install --python``.
    """
    python = sys.executable
    requirement = requirement_for(version)
    has_pip = subprocess.run(
        [python, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0
    if not has_pip:
        uv = shutil.which("uv")
        if uv:
            say(log, "no pip in this environment; using uv")
            return [uv, "pip", "install", "--python", python, "--upgrade", requirement]
        say(log, "no pip in this environment and no uv on PATH; trying pip anyway")
    return [python, "-m", "pip", "install", "--upgrade", requirement]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=None, help="release to install (default: the latest)")
    ap.add_argument("--wait-pid", type=int, required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--stop-flag", required=True)
    ap.add_argument("--relaunch", default="")
    args = ap.parse_args()

    say(args.log, f"waiting for pid {args.wait_pid} to exit")
    if not wait_for_exit(args.wait_pid, 30.0):
        say(args.log, "it did not exit; not upgrading over a running CIRIS")
        return 1
    rc = run(pip_install_argv(args.version, args.log), args.log)
    say(args.log, f"pip exited {rc}")
    # Clears any ~iris* leftovers from an earlier failed upgrade (ciris-server >= 0.5.245).
    run([sys.executable, "-m", "ciris_server.upgrade", "--repair"], args.log)
    try:
        os.remove(args.stop_flag)
    except OSError:
        pass
    if args.relaunch:
        argv = json.loads(args.relaunch)
        say(args.log, f"starting CIRIS again: {argv}")
        subprocess.Popen(argv, close_fds=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
