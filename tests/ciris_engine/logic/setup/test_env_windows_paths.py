r"""Windows paths must survive the .env round-trip — `\f` in a username is not an escape.

A Windows user could not start the agent at all:

    [CIRIS STARTUP] CIRIS_HOME: C:\Users\franc\ciris        <- written correctly
    OSError: [WinError 123] … 'C:\\Users\x0cranc\\ciris\\data'

`\f` + `ranc` became a FORM FEED. python-dotenv applies POSIX escape processing
inside DOUBLE quotes, and the wizard writes every value double-quoted — so a
path containing a backslash followed by `a b f n r t v 0-7 x u U N` is rewritten
on read. The agent then tried to mkdir a path containing a control character and
died before reaching its first service.

The blast radius is large and the failure is total: franc, frank, nancy, nate,
tom, tim, rachel, rob, bob, ben, alice, adam, victor — any of those as the first
character after a backslash. POSIX is unaffected, which is why CI never saw it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values

from ciris_engine.logic.setup.wizard import _env_quoted


@pytest.mark.parametrize(
    "path,escape",
    [
        (r"C:\Users\franc\ciris\data", r"\f form feed — the reported crash"),
        (r"C:\Users\nancy\ciris\data", r"\n newline"),
        (r"C:\Users\tom\ciris\data", r"\t tab"),
        (r"C:\Users\rachel\ciris\data", r"\r carriage return"),
        (r"C:\Users\bob\ciris\data", r"\b backspace"),
        (r"C:\Users\alice\ciris\data", r"\a bell"),
        (r"C:\Users\victor\ciris\data", r"\v vertical tab"),
        (r"C:\Users\007agent\ciris\data", r"\0 octal escape"),
        (r"C:\Users\xavier\ciris\data", r"\x hex escape"),
        ("/home/emoore/ciris/data", "posix — must be unaffected"),
    ],
)
def test_path_survives_the_env_round_trip(path: str, escape: str, tmp_path: Path) -> None:
    """Write it the way the wizard does, read it the way the agent does."""
    env = tmp_path / ".env"
    env.write_text(f'CIRIS_DATA_DIR="{_env_quoted(path)}"\n', encoding="utf-8")

    got = dotenv_values(str(env))["CIRIS_DATA_DIR"]

    assert got == path, f"{escape}: {got!r} != {path!r}"


def test_the_bug_is_real_without_the_helper(tmp_path: Path) -> None:
    """Pin the defect itself, so nobody 'simplifies' the quoting back.

    Without escaping, the exact reported corruption reproduces — this asserts
    the mechanism rather than trusting the description of it.
    """
    env = tmp_path / ".env"
    env.write_text('CIRIS_DATA_DIR="C:\\Users\\franc\\ciris\\data"\n', encoding="utf-8")

    got = dotenv_values(str(env))["CIRIS_DATA_DIR"]

    assert "\x0c" in got, "expected dotenv to eat \\f without escaping — the premise of the fix"
    assert got != r"C:\Users\franc\ciris\data"


def test_embedded_quote_does_not_break_the_line(tmp_path: Path) -> None:
    """A quote in the path must not terminate the value early.

    Windows paths rarely contain quotes, but a value that escapes backslashes
    while leaving quotes raw would produce a subtly truncated path instead of a
    loud failure — the worse outcome.
    """
    weird = r'C:\Users\fra"nc\ciris'
    env = tmp_path / ".env"
    env.write_text(f'CIRIS_DATA_DIR="{_env_quoted(weird)}"\n', encoding="utf-8")

    assert dotenv_values(str(env))["CIRIS_DATA_DIR"] == weird
