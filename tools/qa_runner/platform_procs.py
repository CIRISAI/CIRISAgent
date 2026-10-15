"""Cross-platform process helpers for the QA runner.

WHY THIS EXISTS. The runner shelled out to POSIX-only binaries, so on Windows it
died with

    subprocess.run(["pkill", "-9", "-f", "CIRIS-macos"], ...)
    FileNotFoundError: [WinError 2] The system cannot find the file specified

Two things wrong in one line: `pkill` does not exist on Windows, and the pattern
names a **macOS** binary. The cleanup path had only ever been written for one
platform, which is the same reason the harness imported `pty` unconditionally —
this suite has been maintained against the machine it happened to run on.

`lsof` had the same problem in two more places.

These helpers are deliberately tolerant. They exist to CLEAN UP and to DIAGNOSE;
neither job is worth failing a test run over. A cleanup helper that raises turns
"the previous run left a process behind" into "the suite cannot start", which is
strictly worse than the mess it was tidying.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

IS_WINDOWS = sys.platform == "win32"

#: How long any of these may block. They run between tests, so a hang here
#: stalls the suite for no benefit.
_TIMEOUT = 10


def kill_processes_matching(pattern: str) -> int:
    """Kill processes whose command line contains `pattern`. Returns a best-effort count.

    Never raises. On Windows there is no `pkill`, and `taskkill` matches on IMAGE
    NAME rather than full command line, so the match is necessarily coarser —
    which is fine for the fixed set of names the runner spawns.
    """
    try:
        if IS_WINDOWS:
            # taskkill wants an image name; accept both "foo" and "foo.exe".
            image = pattern if pattern.lower().endswith(".exe") else f"{pattern}.exe"
            r = subprocess.run(
                ["taskkill", "/F", "/IM", image],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            return 1 if r.returncode == 0 else 0
        r = subprocess.run(
            ["pkill", "-9", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return 1 if r.returncode == 0 else 0
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        # No pkill/taskkill, or it misbehaved. Nothing to clean up is the same
        # outcome as failing to clean up, from the caller's point of view.
        return 0


def pids_listening_on(port: int) -> Optional[List[int]]:
    """PIDs listening on `port`, or None when the lookup itself failed.

    THREE ANSWERS, NOT TWO:

      * ``[1234, ...]`` -- these processes hold the port
      * ``[]``          -- a lookup RAN and found no listener: the port is free
      * ``None``        -- could not tell (no lsof/ss/netstat, a timeout, or a
                           listener whose owning process the tool would not name)

    The old contract returned [] for both of the last two, so every caller had
    to print "(could not tell)" even when netstat had run and answered -- which
    is what the desktop-ui diagnosis did on a Windows runner whose port was in
    fact free. Callers must still not read None as "free".
    """
    try:
        if IS_WINDOWS:
            r = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            if r.returncode != 0:
                return None
            pids = []
            for line in r.stdout.splitlines():
                parts = line.split()
                # Proto  Local           Foreign      State       PID
                if len(parts) >= 5 and parts[3].upper() == "LISTENING":
                    if parts[1].rsplit(":", 1)[-1] == str(port):
                        try:
                            pids.append(int(parts[4]))
                        except ValueError:
                            pass
            return sorted(set(pids))
        lsof_answered = False
        try:
            r = subprocess.run(
                ["lsof", "-tiTCP:" + str(port), "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
            pids = sorted({int(x) for x in r.stdout.split() if x.strip().isdigit()})
            if pids:
                return pids
            # lsof exits 1 with no output when nothing matches; anything on
            # stderr, or another code, is lsof failing rather than answering.
            lsof_answered = r.returncode in (0, 1) and not r.stderr.strip()
        except (FileNotFoundError, subprocess.SubprocessError, OSError, ValueError):
            pass
        # `ss` where lsof is absent or answered nothing: minimal Linux images ship
        # iproute2 and not lsof.
        try:
            r = subprocess.run(
                ["ss", "-ltnpH", "sport", "=", f":{port}"],
                capture_output=True,
                text=True,
                timeout=_TIMEOUT,
            )
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            return [] if lsof_answered else None
        if r.returncode != 0:
            return [] if lsof_answered else None
        found = sorted({int(m.group(1)) for m in re.finditer(r"pid=(\d+)", r.stdout)})
        if not found and r.stdout.strip():
            # ss sees a listener but will not name its process (another user's
            # socket without privileges). Held, holder unknown -- NOT free.
            return None
        return found
    except (FileNotFoundError, subprocess.SubprocessError, OSError, ValueError):
        return None


def kill_pids(pids: "List[int]") -> int:
    """Hard-kill `pids`. Returns how many kills were issued. Never raises.

    `os.kill(SIGKILL)` does not exist on Windows, where the equivalent is
    `taskkill /F /PID`. Same tolerance rule as the rest of this module: a
    cleanup helper that raises turns "something was left behind" into "the
    suite cannot start".
    """
    sent = 0
    for pid in pids:
        try:
            if IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=_TIMEOUT,
                )
            else:
                import os
                import signal

                os.kill(pid, signal.SIGKILL)
            sent += 1
        except (FileNotFoundError, subprocess.SubprocessError, OSError, ProcessLookupError):
            continue
    return sent


def desktop_process_pattern() -> str:
    """The desktop app's process name for the CURRENT platform.

    The old code hardcoded `CIRIS-macos` everywhere, so on Windows it hunted a
    process that could never exist — and on Linux, likewise.
    """
    if IS_WINDOWS:
        return "CIRIS-windows"
    if sys.platform == "darwin":
        return "CIRIS-macos"
    return "CIRIS-linux"


def temp_path(name: str) -> Path:
    """A scratch path under the platform's real temp directory.

    `Path("/tmp") / name` is an absolute POSIX path. On Windows it becomes
    `\\tmp\\name` on the current drive -- a directory that does not exist -- so
    opening it for write raises

        FileNotFoundError: [Errno 2] No such file or directory: '\\tmp\\ciris_desktop_setup.log'

    which is what killed Boot 1 immediately after the server came up healthy.
    tempfile.gettempdir() honours TMPDIR/TEMP/TMP and falls back sensibly, so it
    is right on all three platforms and respects a runner's configured scratch
    space rather than assuming one.
    """
    return Path(tempfile.gettempdir()) / name
