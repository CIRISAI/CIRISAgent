#!/usr/bin/env python3
"""How much memory is the agent's backend (agent + embedded node) holding?

WHY THIS EXISTS. ciris-server 0.5.222 raised the canonical's resting RSS from
~800 MB to ~1.3 GB and nobody yet knows how much of that is per-node. The
agent's node is folded into the backend process (desktop: `main.py --adapter
api`; Android/iOS: the app process), so the backend's resident memory is the
number a 4 GB laptop or a phone actually pays. The five-platform run already
stands every platform up with real activity behind it; this reads the backend's
memory while it is still standing, then again after an idle minute, so a
release can be compared with the one before it.

REPORT-ONLY. It never fails the gate: a number that cannot be read is written
as null with the reason, because a missing sample is not a regression.

Usage:
    sample_backend_memory.py --platform linux --target linux --out artifacts/memory-linux.json
    sample_backend_memory.py --platform android --target android --idle-secs 60 --out ...
"""


import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel

ANDROID_PACKAGE = "ai.ciris.mobile.debug"
# A simulator app runs as a host process whose executable lives in the .app.
IOS_EXECUTABLE_MARKER = "iosApp.app"

MB = 1024 * 1024


class MemorySample(BaseModel):
    """One reading of the backend. Both numbers null means it could not be read."""

    rss_mb: Optional[float] = None
    pss_mb: Optional[float] = None
    pid: Optional[int] = None
    matches: Optional[int] = None
    source: Optional[str] = None
    reason: Optional[str] = None

    def describe(self) -> str:
        if self.rss_mb is None and self.pss_mb is None:
            return f"unavailable ({self.reason or 'unknown'})"
        parts = [f"rss={self.rss_mb} MB"] if self.rss_mb is not None else []
        if self.pss_mb is not None:
            parts.append(f"pss={self.pss_mb} MB")
        return " ".join(parts)


class MemoryReport(BaseModel):
    platform: str
    target: str
    ciris_server: Optional[str]
    idle_secs: int
    after_activity: MemorySample
    resting: MemorySample


def _adb() -> Optional[str]:
    found = shutil.which("adb")
    if found:
        return found
    import os

    sdk = os.environ.get("ANDROID_HOME") or "/usr/local/lib/android/sdk"
    candidate = Path(sdk) / "platform-tools" / "adb"
    return str(candidate) if candidate.exists() else None


def parse_dumpsys_meminfo(text: str) -> Tuple[Optional[float], Optional[float]]:
    """(rss_mb, pss_mb) from `dumpsys meminfo <pkg>`; values are reported in KB.

    Newer Android prints `TOTAL PSS: n ... TOTAL RSS: n` on one line; older
    releases print a `TOTAL` row in the table whose first number is PSS.
    """
    pss = re.search(r"TOTAL PSS:\s*(\d+)", text)
    rss = re.search(r"TOTAL RSS:\s*(\d+)", text)
    pss_kb: Optional[int] = int(pss.group(1)) if pss else None
    rss_kb: Optional[int] = int(rss.group(1)) if rss else None
    if pss_kb is None:
        row = re.search(r"^\s*TOTAL\s+(\d+)", text, re.MULTILINE)
        if row:
            pss_kb = int(row.group(1))
    return (
        round(rss_kb / 1024, 1) if rss_kb is not None else None,
        round(pss_kb / 1024, 1) if pss_kb is not None else None,
    )


def sample_android() -> MemorySample:
    adb = _adb()
    if adb is None:
        return MemorySample(reason="adb not found")
    proc = subprocess.run(
        [adb, "shell", "dumpsys", "meminfo", ANDROID_PACKAGE], capture_output=True, text=True, timeout=60
    )
    rss_mb, pss_mb = parse_dumpsys_meminfo(proc.stdout)
    if rss_mb is None and pss_mb is None:
        return MemorySample(reason=f"no TOTAL in dumpsys meminfo (rc={proc.returncode})")
    return MemorySample(rss_mb=rss_mb, pss_mb=pss_mb, source=f"dumpsys meminfo {ANDROID_PACKAGE}")


def is_backend_cmdline(cmdline: List[str], target: str) -> bool:
    joined = " ".join(cmdline)
    if target == "ios":
        return IOS_EXECUTABLE_MARKER in joined
    # Desktop: the backend `ciris-agent` spawns, which hosts the folded node.
    # Split on both separators: a Windows backend's path must parse wherever
    # the sampler runs, and Path() on POSIX does not split backslashes.
    names = [re.split(r"[\\/]", part)[-1] for part in cmdline]
    return "main.py" in names and "--adapter" in cmdline and "api" in cmdline


def sample_host_process(target: str) -> MemorySample:
    try:
        import psutil
    except ImportError:
        return MemorySample(reason="psutil not installed")
    matches: List[Tuple[int, int]] = []
    for proc in psutil.process_iter(["pid", "cmdline", "memory_info"]):
        try:
            cmdline = proc.info["cmdline"] or []
            if cmdline and is_backend_cmdline(cmdline, target):
                matches.append((proc.info["pid"], proc.info["memory_info"].rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if not matches:
        return MemorySample(reason=f"no {target} backend process found")
    # The largest match is the backend; a launcher or wrapper is a fraction of it.
    pid, rss = max(matches, key=lambda m: m[1])
    return MemorySample(rss_mb=round(rss / MB, 1), pid=pid, matches=len(matches), source="psutil rss")


def sample(target: str) -> MemorySample:
    try:
        return sample_android() if target == "android" else sample_host_process(target)
    except Exception as exc:  # report-only: a sampler error is data, not a gate failure
        return MemorySample(reason=f"{type(exc).__name__}: {exc}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--platform", required=True, help="matrix platform label (linux, macos, windows, android, ios)")
    parser.add_argument("--target", required=True, help="android, ios, or a desktop OS name")
    parser.add_argument("--idle-secs", type=int, default=60, help="idle wait before the resting sample")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    after_activity = sample(args.target)
    time.sleep(max(args.idle_secs, 0))
    resting = sample(args.target)

    try:
        import importlib.metadata as metadata

        server_version: Optional[str] = metadata.version("ciris-server")
    except Exception:
        server_version = None

    report = MemoryReport(
        platform=args.platform,
        target=args.target,
        ciris_server=server_version,
        idle_secs=args.idle_secs,
        after_activity=after_activity,
        resting=resting,
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(report.model_dump_json(indent=2) + "\n")

    print(
        f"::notice::{args.platform} backend memory (ciris-server {server_version}): "
        f"after activity {after_activity.describe()}; resting after {args.idle_secs}s {resting.describe()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
