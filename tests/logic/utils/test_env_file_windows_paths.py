"""A Windows path must survive a write/read round-trip through `.env`.

THE BUG, REPORTED TWICE BY A REAL USER.

    C:\\Users\\franc\\ciris          written
    C:\\Users\\x0cranc\\ciris        read back
    OSError: [WinError 123] ...

python-dotenv applies POSIX escape processing inside DOUBLE quotes, so `\\f`
became a FORM FEED and the agent tried to mkdir a path containing a control
character — dying before its first service started. Total failure, not a
degradation.

2.9.17 fixed `setup/wizard.py`. The user hit it AGAIN, because the desktop and
mobile wizards drive `routes/setup/complete.py`, which had twenty raw f-string
writes of its own. Fixing one call site does not fix a defect that belongs to
every call site, which is why the escaping now lives in the line-builder.

These tests round-trip through dotenv itself rather than asserting on the
escaped string, because the whole defect was that writing and reading disagreed
— an assertion written against either side alone would have passed while the
pair stayed broken.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ciris_engine.logic.utils.env_file import env_line, env_quoted

#: Every one of these is a real Windows home whose second character triggers an
#: escape: \f form feed, \n newline, \t tab, \r CR, \b backspace, \v vertical
#: tab, \a bell, \0 null, \x hex, \u unicode.
WINDOWS_PATHS = [
    r"C:\Users\franc\ciris",       # \f — the reported one
    r"C:\Users\frank\ciris\data",
    r"C:\Users\nancy\ciris",       # \n
    r"C:\Users\tom\ciris",         # \t
    r"C:\Users\rachel\ciris",      # \r
    r"C:\Users\ben\ciris",         # \b
    r"C:\Users\victor\ciris",      # \v
    r"C:\Users\alice\ciris",       # \a
    r"C:\Users\0scar\ciris",       # \0
    r"C:\Users\xavier\ciris",      # \x
    r"C:\Users\uma\ciris",         # \u
    r"C:\Program Files\CIRIS\verify.exe",
    r"\\server\share\ciris",       # UNC
]


def _roundtrip(tmp_path: Path, key: str, value: str) -> str | None:
    """Write via our builder, read via dotenv — exactly the production pair."""
    dotenv = pytest.importorskip("dotenv")
    env = tmp_path / ".env"
    env.write_text(env_line(key, value), encoding="utf-8")
    return dotenv.dotenv_values(str(env)).get(key)


@pytest.mark.parametrize("path", WINDOWS_PATHS)
def test_windows_paths_survive_the_roundtrip(tmp_path: Path, path: str) -> None:
    assert _roundtrip(tmp_path, "CIRIS_HOME", path) == path


@pytest.mark.parametrize("path", WINDOWS_PATHS)
def test_no_control_character_is_ever_produced(tmp_path: Path, path: str) -> None:
    """The failure mode was a CONTROL CHARACTER in a path, so name it directly.

    Equality above would catch this too, but this assertion says what actually
    broke the install — and would still fire if someone 'fixed' the comparison.
    """
    got = _roundtrip(tmp_path, "CIRIS_HOME", path) or ""
    offenders = {c for c in got if ord(c) < 32}
    assert not offenders, f"control characters {[hex(ord(c)) for c in offenders]} in {got!r}"


def test_the_exact_reported_failure(tmp_path: Path) -> None:
    """Pinned verbatim, so this specific regression can never come back quietly."""
    got = _roundtrip(tmp_path, "CIRIS_HOME", r"C:\Users\franc\ciris")
    assert got == r"C:\Users\franc\ciris"
    assert "\x0c" not in (got or ""), "form feed — the 2.9.17 bug, third occurrence"


def test_embedded_quotes_survive(tmp_path: Path) -> None:
    """Backslash-then-quote ordering: escaping quotes first would double-escape."""
    value = r'C:\Users\franc\My "CIRIS" Folder'
    assert _roundtrip(tmp_path, "CIRIS_HOME", value) == value


def test_ordinary_posix_values_are_untouched(tmp_path: Path) -> None:
    """The fix must not disturb the platform where nothing was wrong."""
    for value in ("/home/emoore/ciris", "sk-abc123", "http://127.0.0.1:8080/v1", ""):
        assert _roundtrip(tmp_path, "K", value) == value


def test_none_becomes_empty_not_the_string_none(tmp_path: Path) -> None:
    """`None` reaching a writer must not persist the literal text "None"."""
    assert env_quoted(None) == ""


def test_complete_py_has_no_raw_quoted_writes() -> None:
    """Structural guard: the defect returns the moment someone adds an f-string.

    Asserting on the SOURCE because that is where the mistake is made. The
    round-trip tests above cannot see a write site that does not exist yet.
    """
    import inspect
    import re

    from ciris_engine.logic.adapters.api.routes.setup import complete

    src = inspect.getsource(complete)
    raw = re.findall(r"""f\.write\(f'[A-Z0-9_]+="\{""", src)
    assert not raw, f"{len(raw)} raw quoted .env write(s) — use env_line() instead"


# ---------------------------------------------------------------------------
# The env-SYNC round trip — the third site, and the one that re-corrupted a
# clean install. `path_resolution.persist_env_var` reads the WHOLE .env,
# sanitizes every value, and writes it back. So the escape/decode pair has to
# be an exact inverse, and has to stay stable across MANY rewrites, because it
# runs on every boot.
# ---------------------------------------------------------------------------


def _sync_once(env_path: Path) -> None:
    from ciris_engine.logic.utils.path_resolution import (
        _parse_and_sanitize_env_content,
        _reconstruct_env_content,
    )

    parsed = _parse_and_sanitize_env_content(env_path.read_text(encoding="utf-8"))
    env_path.write_text(_reconstruct_env_content(parsed), encoding="utf-8")


@pytest.mark.parametrize("path", WINDOWS_PATHS)
def test_env_sync_does_not_corrupt_a_correctly_written_path(tmp_path: Path, path: str) -> None:
    """THE FRANK BUG: the wizard wrote it right, then the sync broke it.

    Before the fix `_sanitize_env_value` ended with

        sanitized.replace("\\\\", "\\")

    which COLLAPSES double backslashes — the opposite of its own comment. It
    parsed the wizard's escaped value, un-escaped it, and wrote it back bare.
    dotenv then read `\\f` as a form feed. Wiping the CIRIS folder did not help,
    because the sync re-corrupted the freshly-written file.
    """
    dotenv = pytest.importorskip("dotenv")
    env = tmp_path / ".env"
    env.write_text(env_line("CIRIS_DATA_DIR", path), encoding="utf-8")

    _sync_once(env)

    assert dotenv.dotenv_values(str(env))["CIRIS_DATA_DIR"] == path


@pytest.mark.parametrize("path", [r"C:\Users\franc\ciris\data", r"\\server\share\ciris"])
def test_repeated_syncs_do_not_drift(tmp_path: Path, path: str) -> None:
    """Stability across MANY rewrites, not just one.

    The opposite-sign failure is quieter than the form feed and would survive a
    single-round-trip test: escaping without a matching decode grows one
    backslash pair per sync, so the path only stops resolving after several
    boots. This runs the sync ten times.
    """
    dotenv = pytest.importorskip("dotenv")
    env = tmp_path / ".env"
    env.write_text(env_line("CIRIS_DATA_DIR", path), encoding="utf-8")

    for i in range(10):
        _sync_once(env)
        got = dotenv.dotenv_values(str(env))["CIRIS_DATA_DIR"]
        assert got == path, f"drifted on sync {i + 1}: {got!r}"


def test_env_quoted_and_env_unquoted_are_exact_inverses() -> None:
    """The pair is the contract; assert it directly rather than via a file."""
    from ciris_engine.logic.utils.env_file import env_quoted, env_unquoted

    for value in WINDOWS_PATHS + [r'C:\a\b "quoted" \c', "", "plain", "/posix/path", "a\\\\b"]:
        assert env_unquoted(env_quoted(value)) == value, f"not an inverse for {value!r}"


# ---------------------------------------------------------------------------
# REPAIR ON READ. 2.9.19 fixed the writers, which stops NEW corruption and does
# nothing for the .env files already on disk. A user installed 2.9.19 and hit
# the IDENTICAL WinError 123, because his file was poisoned by an earlier
# version. Fixing the writers and fixing the USERS are two different problems.
# ---------------------------------------------------------------------------

POISONED = {
    "C:\\Users\x0cranc\\ciris\\data": r"C:\Users\franc\ciris\data",   # \f — reported
    "C:\\Users\x0bictor\\ciris": r"C:\Users\victor\ciris",            # \v
    "C:\\Users\tom\\ciris": r"C:\Users\tom\ciris",                    # \t
    "C:\\Users\rachel\\ciris": r"C:\Users\rachel\ciris",              # \r
    "C:\\Users\nancy\\ciris": r"C:\Users\nancy\ciris",                # \n
    "C:\\Users\x08en\\ciris": r"C:\Users\ben\ciris",                  # \b
    "C:\\Users\x07lice\\ciris": r"C:\Users\alice\ciris",              # \a
}


@pytest.mark.parametrize("poisoned,expected", sorted(POISONED.items()))
def test_a_poisoned_value_is_repaired(poisoned: str, expected: str) -> None:
    from ciris_engine.logic.utils.env_file import repair_dotenv_escapes

    assert repair_dotenv_escapes(poisoned) == expected


def test_repair_is_idempotent_and_leaves_clean_values_alone() -> None:
    """Runs on every read, so it must never degrade an already-good value."""
    from ciris_engine.logic.utils.env_file import repair_dotenv_escapes

    for clean in (r"C:\Users\franc\ciris", "C:/Users/franc/ciris", "/home/e/ciris", ""):
        assert repair_dotenv_escapes(clean) == clean
    once = repair_dotenv_escapes("C:\\Users\x0cranc")
    assert repair_dotenv_escapes(once) == once


def test_get_env_var_repairs_path_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """The assertion that matters: the CALLER must get a usable path.

    The standalone helper passing while `get_env_var` returned the corrupted
    value is precisely the shape of this bug — a fix verified at the wrong layer.
    """
    import ciris_engine.logic.config.env_utils as eu

    monkeypatch.setattr(eu, "_ENV_LOADED", True, raising=False)
    monkeypatch.setenv("CIRIS_DB_PATH", "C:\\Users\x0cranc\\ciris\\data\\ciris_engine.db")

    got = eu.get_env_var("CIRIS_DB_PATH")

    assert got == r"C:\Users\franc\ciris\data\ciris_engine.db"
    assert not [c for c in got if ord(c) < 32]


def test_non_path_keys_are_left_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only PATH values are repaired — elsewhere a control char may be deliberate."""
    import ciris_engine.logic.config.env_utils as eu

    monkeypatch.setattr(eu, "_ENV_LOADED", True, raising=False)
    monkeypatch.setenv("SOME_OTHER_VALUE", "keep\x0cthis")

    assert eu.get_env_var("SOME_OTHER_VALUE") == "keep\x0cthis"


def test_the_repair_log_does_not_print_the_path(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    """The value is user data, and the corrupted form has been through enough logs."""
    import ciris_engine.logic.config.env_utils as eu

    monkeypatch.setattr(eu, "_ENV_LOADED", True, raising=False)
    monkeypatch.setenv("CIRIS_DB_PATH", "C:\\Users\x0cranc\\ciris\\data")

    with caplog.at_level("WARNING"):
        eu.get_env_var("CIRIS_DB_PATH")

    assert "CIRIS_DB_PATH" in caplog.text
    assert "franc" not in caplog.text


def test_wizard_written_key_spellings_are_repaired(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wizard writes SECRETS_DB_PATH; the config layer reads CIRIS_SECRETS_DB_PATH.

    Those names do not match — a real bug of its own — and it means a repair set
    built from either side alone misses half the keys. A live user's .env had
    exactly these two lines still carrying backslashes.
    """
    import ciris_engine.logic.config.env_utils as eu

    monkeypatch.setattr(eu, "_ENV_LOADED", True, raising=False)
    for key in ("SECRETS_DB_PATH", "AUDIT_LOG_PATH", "CIRIS_SECRETS_DB_PATH", "CIRIS_AUDIT_DB_PATH"):
        monkeypatch.setenv(key, "C:\\Users\x0cranc\\ciris\\data\\x.db")
        assert eu.get_env_var(key) == r"C:\Users\franc\ciris\data\x.db", key


@pytest.mark.parametrize("path", WINDOWS_PATHS)
def test_env_path_value_removes_the_hazard_entirely(path: str) -> None:
    """Forward slashes cannot be mangled, by construction.

    Escaping is a rule every writer has to remember, and three separate sites
    got it wrong. A value with no backslashes needs no rule — this is the belt
    to env_quoted's braces.
    """
    from ciris_engine.logic.utils.env_file import env_path_value

    v = env_path_value(path)
    assert "\\" not in v


def test_forward_slash_paths_roundtrip_untouched(tmp_path: Path) -> None:
    """And they survive the write/read pair with no escaping needed at all."""
    dotenv = pytest.importorskip("dotenv")
    from ciris_engine.logic.utils.env_file import env_path_value

    v = env_path_value(r"C:\Users\franc\ciris\data")
    env = tmp_path / ".env"
    env.write_text(env_line("CIRIS_DATA_DIR", v), encoding="utf-8")

    got = dotenv.dotenv_values(str(env))["CIRIS_DATA_DIR"]
    assert got == "C:/Users/franc/ciris/data"
    assert not [c for c in got if ord(c) < 32]
