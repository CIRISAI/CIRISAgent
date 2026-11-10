"""Runs pip for ``ciris-agent upgrade``, from OUTSIDE the install it replaces.

STANDARD LIBRARY ONLY, and never imported from the package: ciris_engine.upgrade
copies this file to a temp directory and runs it with a bare interpreter, because
on Windows anything running from site-packages, or from Scripts\\ciris-agent.exe,
is a file pip can't move. pip then fails part way through (WinError 32) and leaves
a half-installed agent that dies at import.

    python helper.py --python <exe> --requirement ciris-agent --wait-pid N --log F [--relaunch JSON]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import List


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True)
    ap.add_argument("--requirement", required=True)
    ap.add_argument("--wait-pid", type=int, required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--stop-flag", required=True)
    ap.add_argument("--relaunch", default="")
    args = ap.parse_args()

    say(args.log, f"waiting for pid {args.wait_pid} to exit")
    if not wait_for_exit(args.wait_pid, 30.0):
        say(args.log, "it did not exit; not upgrading over a running CIRIS")
        return 1
    rc = run([args.python, "-m", "pip", "install", "--upgrade", args.requirement], args.log)
    say(args.log, f"pip exited {rc}")
    # Clears any ~iris* leftovers from an earlier failed upgrade (ciris-server >= 0.5.245).
    run([args.python, "-m", "ciris_server.upgrade", "--repair"], args.log)
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
