"""Windows console UTF-8 shim.

The CIRIS backend prints status glyphs (✓, ✗, ⚠, 🎉, …) via `logger` and
`print` during startup — adapter load, DB init, service warmup. On a default
Windows 10/11 console (cmd.exe, PowerShell) the active code page is cp1252 or
cp850, and Python 3.12 binds ``sys.stdout`` / ``sys.stderr`` to that encoding.
Any non-ASCII glyph raises ``UnicodeEncodeError`` and, when it happens inside
error paths (DB init, adapter bootstrap), crashes the whole process.

This module flips the active console to UTF-8 and reconfigures the Python
stdio wrappers to match, idempotently and safely. It is a no-op on non-Windows
platforms and on closed / non-TextIOWrapper streams.

Call ``setup()`` as the first side-effect of each process entry point
(``main.py``, ``ciris_engine/cli.py``, ``ciris_engine/desktop_launcher.py``,
and ``logging_config.setup_basic_logging``) so that every stream a logging
handler or ``print`` call might touch has already been reconfigured.

When a child process is spawned, propagate the intent via
``subprocess_env()`` so the grandchild inherits PYTHONUTF8=1 +
PYTHONIOENCODING=utf-8.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping, MutableMapping

_APPLIED = False


def _reconfigure_stream(stream: object) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        pass


def _set_console_code_page_utf8() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        windll = getattr(ctypes, "windll", None)
        if windll is not None:
            kernel32 = windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
    except (OSError, AttributeError):
        pass


def setup() -> None:
    """Install the UTF-8 stdio shim. Idempotent; no-op off Windows."""
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    if sys.platform != "win32":
        return

    _set_console_code_page_utf8()
    _reconfigure_stream(sys.stdout)
    _reconfigure_stream(sys.stderr)


def subprocess_env(base: Mapping[str, str] | None = None) -> MutableMapping[str, str]:
    """Return an env mapping suitable for spawning a Python subprocess.

    Starts from ``base`` (or ``os.environ`` if None) and injects PYTHONUTF8=1 /
    PYTHONIOENCODING=utf-8 so the child interpreter's stdio also uses UTF-8,
    regardless of the active console code page. Safe on all platforms —
    PYTHONUTF8 is a no-op off Windows and the vars are harmless elsewhere.
    """
    env: MutableMapping[str, str] = dict(os.environ if base is None else base)
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
