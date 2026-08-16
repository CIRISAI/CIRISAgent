"""Terminate this process immediately, on every platform we support.

WHY THIS EXISTS. The ACCORD kill switch terminated with

    os.kill(os.getpid(), signal.SIGKILL)

and `signal.SIGKILL` DOES NOT EXIST ON WINDOWS. Evaluating the attribute raises
`AttributeError` before `os.kill` is ever called, so on Windows the kill switch
did not kill anything.

That is bad in four places and genuinely dangerous in one. In
`base_observer._check_for_accord` the call sits INSIDE `except Exception`:

    except Exception as e:
        logger.critical("... Agent cannot operate with broken kill switch. TERMINATING.")
        os.kill(os.getpid(), signal.SIGKILL)      # AttributeError on Windows

so the termination raises, the exception escapes into
`handle_incoming_message`, and the adapter's message loop catches it like any
other bad message. The agent logs that it cannot be trusted and then keeps
running -- which is precisely the state the code exists to prevent. It fails
OPEN, and silently.

WHY os._exit AND NOT sys.exit. SIGKILL cannot be caught, blocked or ignored;
that is the entire reason the kill switch uses it. `sys.exit()` only raises
`SystemExit`, which any `except BaseException` -- or a bare `except:` in a
plugin, an adapter, or a third-party library on the stack -- will swallow. A
kill switch that a downstream `try` can veto is not a kill switch. `os._exit()`
is the Windows primitive with the right semantics: immediate, no unwinding, no
`finally`, no `atexit`, uncatchable.

The exit code is 137 rather than 1, because that is what a shell reports for a
SIGKILLed process (128 + 9). Supervisors, container runtimes and CI then see the
same code from both platforms instead of Windows reporting a generic failure.

WHY WE FLUSH FIRST. Both primitives skip interpreter cleanup, so buffered log
records die with the process -- including the CRITICAL line saying why. Every
one of these call sites logs its reason immediately before terminating, and that
line is the only forensic evidence anyone gets. Flushing is best-effort and
wrapped: a broken handler must not be able to prevent the kill.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from typing import NoReturn

logger = logging.getLogger(__name__)

#: 128 + SIGKILL(9), the exit status a shell reports for a killed process. Used
#: on Windows too so supervisors see one code from both platforms.
KILLED_EXIT_CODE = 137


def _flush_logs() -> None:
    """Best-effort flush. Never raises -- a bad handler must not veto a kill."""
    try:
        for handler in list(logging.getLogger().handlers):
            try:
                handler.flush()
            except Exception:
                pass
        for stream in (sys.stdout, sys.stderr):
            try:
                if stream is not None:
                    stream.flush()
            except Exception:
                pass
    except Exception:
        pass


def terminate_immediately(reason: str) -> NoReturn:
    """Kill this process now. Does not return, and cannot be caught.

    Args:
        reason: Logged CRITICAL before terminating. This is the only record that
            survives, so it must say what tripped the switch.
    """
    try:
        logger.critical("TERMINATING IMMEDIATELY: %s", reason)
    except Exception:
        pass

    _flush_logs()

    # POSIX: uncatchable by construction.
    if hasattr(signal, "SIGKILL"):
        try:
            os.kill(os.getpid(), signal.SIGKILL)  # NOSONAR python:S4828 - own pid only
        except Exception:
            # Should be unreachable; fall through rather than leave the process
            # alive because the primitive we preferred misbehaved.
            pass

    # Windows, and the POSIX fall-through. Not sys.exit(): SystemExit is
    # catchable and this must not be.
    os._exit(KILLED_EXIT_CODE)
