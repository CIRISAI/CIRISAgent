"""Writing `.env` lines that survive being read back.

python-dotenv applies POSIX escape processing inside DOUBLE quotes, so a value
written verbatim is not the value that comes back. On Windows this is total:

    CIRIS_HOME: C:\\Users\\franc\\ciris                <- written correctly
    OSError: [WinError 123] ... 'C:\\Users\\x0cranc\\ciris\\data'   <- read back

`\\f` + `ranc` became a FORM FEED. The agent then tried to mkdir a path
containing a control character and died before reaching its first service.

It hits any Windows user whose path contains a backslash followed by one of
`a b f n r t v 0-7 x u U N` — franc, frank, nancy, nate, tom, tim, rachel, rob,
bob, ben, alice, adam, victor. A large share of Windows home directories, and
the failure is total: the agent cannot start at all.

WHY THIS MODULE EXISTS RATHER THAN A FIX AT EACH SITE. 2.9.17 fixed this in
`setup/wizard.py` and the bug came back on a DIFFERENT path — the API
`setup/complete.py`, which is what the desktop and mobile wizards actually
drive, and which had twenty raw f-string writes of its own. Escaping is not a
property of one call site; it is a property of writing a `.env` line at all. So
the escaping lives with the line-builder, and the correct thing is the easy
thing.

`env_line` is the API to reach for. `env_quoted` is exposed for the handful of
callers that assemble a line themselves.
"""

from __future__ import annotations


def env_quoted(value: object) -> str:
    """Escape a value for use inside a DOUBLE-QUOTED `.env` line.

    Backslashes first, then quotes — the reverse order would double-escape the
    backslash introduced by the quote escape.
    """
    text = "" if value is None else str(value)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def env_line(key: str, value: object) -> str:
    """A complete `KEY="value"` line, escaped, newline included.

    Use this instead of an f-string. The whole defect class is that writing and
    reading disagreed about escapes, and a helper that returns the entire line
    leaves no seam for a caller to get the quoting subtly right and the escaping
    wrong.
    """
    return f'{key}="{env_quoted(value)}"\n'


def env_unquoted(value: str) -> str:
    """Reverse `env_quoted` — decode a value read back from a quoted `.env` line.

    Needed because anything that PARSES a `.env` and REWRITES it round-trips
    every value through both halves, and the two must be exact inverses.
    `path_resolution.persist_env_var` does precisely that: it reads the whole
    file, sanitizes, and writes it back.

    Get this wrong in either direction and a Windows path degrades on every
    sync. Under-escaping gave `C:\\Users\\franc` -> a FORM FEED on read (the
    original bug). Escaping without a matching decode gives the opposite:
    `C:\\\\Users\\\\franc` growing another pair of backslashes on every single
    rewrite, until the path stops resolving. Same defect, opposite sign, and the
    second one is quieter because it never produces a control character.

    Backslash LAST here, mirroring `env_quoted` doing it first.
    """
    return value.replace('\\"', '"').replace("\\\\", "\\")


#: dotenv's POSIX escape set, inverted. `\f` + `ranc` became one FORM FEED on
#: read, so mapping the control character back to the two characters that
#: produced it reconstructs the original text exactly.
_ESCAPE_SOURCE = {
    "\x07": r"\a",
    "\x08": r"\b",
    "\x0c": r"\f",
    "\n": r"\n",
    "\r": r"\r",
    "\t": r"\t",
    "\x0b": r"\v",
    "\x00": r"\0",
}


def repair_dotenv_escapes(value: str) -> str:
    """Undo escape processing that a `.env` read applied to a Windows path.

    WHY THIS IS NEEDED AFTER THE WRITE SIDE WAS FIXED. Escaping the writers
    stops NEW corruption; it does nothing for the `.env` files already on disk.
    Every Windows user whose home directory triggers an escape holds a file
    poisoned by an earlier version, and on upgrade gets the identical failure:

        CIRIS_DB_PATH read back as C:\\Users\\<FF>ranc\\ciris\\data\\...
        OSError: [WinError 123]

    A user hit exactly this AFTER installing the release that fixed the writers,
    which is how we learned that fixing the writers and fixing the USERS are two
    different problems. The upgrade alone has to be enough.

    The inverse is exact: dotenv turned `\\f` into a form feed, and a control
    character in this position can only have come from the two-character escape
    that produced it. So `C:\\Users\\<FF>ranc` becomes `C:\\Users\\franc` again.

    SAFE BECAUSE OF WHERE IT IS APPLIED — config values naming a FILESYSTEM
    PATH. A control character is not legal in a Windows path (WinError 123 is
    the OS saying so), so there is no value this can damage. Deliberately not
    applied to arbitrary config, where a control character might be intentional.

    Idempotent: a repaired value has no control characters left to match.
    """
    if not value or not any(ord(c) < 32 for c in value):
        return value
    out = value
    for ctrl, source in _ESCAPE_SOURCE.items():
        out = out.replace(ctrl, source)
    return out


def env_path_value(path: object) -> str:
    """Render a filesystem path for a `.env` line, backslash-free.

    Windows accepts forward slashes everywhere — `os`, `pathlib`, `open`, and
    the Win32 API all normalise them — so writing `C:/Users/franc/ciris` instead
    of `C:\\Users\\franc\\ciris` costs nothing and removes the hazard by
    construction: a value with no backslashes cannot be mangled by escape
    processing, no matter which writer produces it or which reader consumes it.

    This is the belt to `env_quoted`'s braces. Escaping is a rule every writer
    must remember; forward slashes are a property of the value itself. Three
    separate sites got the escaping wrong before this existed, so the value not
    needing the rule is worth more than the rule being applied correctly.
    """
    return str(path).replace("\\", "/")
