"""Point `latest.log` / `incidents_latest.log` at the current file, on any platform.

THE BUG. Both log handlers created their "latest" pointer with

    latest_link.symlink_to(log_filename.name)

wrapped in `except Exception: pass`. On Windows, creating a symlink requires
either Developer Mode or elevation; an ordinary user gets

    OSError: [WinError 1314] A required privilege is not held by the client

so the call failed, the exception was swallowed, and NO latest.log or
incidents_latest.log was created at all.

Nothing crashed, which is why this went unnoticed -- and it broke the single
most-used debugging entry point we have. Our own runbook opens with "ALWAYS
check incidents_latest.log FIRST", the QA runner's log collection expects both
files, and every Windows bug report so far arrived without the one file that
would have explained it. The failure mode was: ask a user for their incidents
log, and they do not have one.

THE FALLBACK CHAIN, best first:

  1. SYMLINK. Points at a NAME, so it keeps resolving correctly across
     RotatingFileHandler rotation -- the name is re-created, the link follows.
     Preferred wherever it is permitted.

  2. HARDLINK. Needs no privilege on NTFS for two files on one volume, which is
     always the case here since both live in the same log directory. Live view
     of the same bytes, so `tail` behaves. It binds to the FILE rather than the
     name, so after a rotation it keeps showing the rotated-out file until the
     next call refreshes it -- worse than a symlink, enormously better than
     nothing.

  3. POINTER FILE. If even hardlinks are refused (FAT32, a network share, a
     container bind mount), write the target path as text. Not a live view, but
     it answers "which file do I open", which is the actual question.

Only step 3 failing is a real failure, and even then this returns rather than
raising: logging setup must never be able to prevent a process from starting.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

LinkKind = Literal["symlink", "hardlink", "pointer", "failed"]


def _clear(link_path: Path) -> None:
    """Remove whatever is there now, including a dangling symlink.

    `exists()` follows symlinks and returns False for a broken one, so
    `is_symlink()` has to be checked separately or a dangling link survives and
    every later attempt fails with FileExistsError.
    """
    try:
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
    except OSError:
        pass


def link_latest(link_path: Path, target: Path) -> LinkKind:
    """Make `link_path` resolve to `target`. Returns which mechanism was used.

    Args:
        link_path: e.g. logs/latest.log
        target: the real file, e.g. logs/ciris_2026-08-16.log
    """
    _clear(link_path)

    # 1. Symlink -- survives rotation because it points at the name.
    try:
        link_path.symlink_to(target.name)
        return "symlink"
    except (OSError, NotImplementedError):
        pass

    # 2. Hardlink -- unprivileged on NTFS, same volume by construction here.
    _clear(link_path)
    try:
        os.link(target, link_path)
        return "hardlink"
    except (OSError, NotImplementedError, AttributeError):
        pass

    # 3. Pointer file -- answers "which file do I open".
    _clear(link_path)
    try:
        link_path.write_text(
            f"{target.resolve()}\n"
            "\n"
            "This is a POINTER FILE, not a log. This platform permitted neither a\n"
            "symlink nor a hardlink, so the path above names the real log file.\n",
            encoding="utf-8",
        )
        return "pointer"
    except OSError as e:
        # Never raise: logging setup must not be able to stop the process.
        logger.warning("Could not create %s by any mechanism: %s", link_path.name, e)
        return "failed"
