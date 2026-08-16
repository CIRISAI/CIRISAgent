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
