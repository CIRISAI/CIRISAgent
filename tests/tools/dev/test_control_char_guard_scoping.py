"""The .env control-character guard must tell three states apart.

It exists because a Windows home like `C:\\Users\\franc\\ciris` contains `\\f`,
and python-dotenv unescapes double-quoted values on read — so a correctly written
path came back with a FORM FEED in it and the agent died on mkdir before reaching
its first service (WinError 123).

The guard therefore refuses to report success unless the risky path was actually
constructed. That is right, and it caught a real vacuous pass. But it treated
"this flow wrote no paths at all" as the same fact as "paths were written and
none of them came from the home we pinned", which made it UNPASSABLE on the
UI setup flow — that flow persists only CIRIS_CONFIGURED, so there is nothing to
corrupt. It failed a run where nothing was wrong, printing a remedy for a bug
that had already been fixed.

A guard that cannot pass gets ignored, which costs more than the guard is worth.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[3] / "tools" / "dev" / "assert_no_control_chars_in_env.py"


def _run(home: Path, label: str = "t") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), "--home", str(home), "--label", label],
        capture_output=True,
        text=True,
    )


def _home_with_env(tmp_path: Path, body: str) -> Path:
    # A home whose own name carries the escape trigger, as the CI job pins.
    home = tmp_path / "franc" / "ciris"
    home.mkdir(parents=True)
    (home / ".env").write_text(body, encoding="utf-8")
    return home


def test_a_flow_that_persists_no_paths_passes(tmp_path: Path) -> None:
    """The UI setup flow writes only CIRIS_CONFIGURED. Nothing to corrupt."""
    home = _home_with_env(tmp_path, 'CIRIS_CONFIGURED="true"\n')
    result = _run(home)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no path values" in result.stdout


def test_paths_written_but_none_from_our_home_still_fails(tmp_path: Path) -> None:
    """THE vacuous pass. Paths exist, so this flow does write them — but none

    derive from the pinned home, meaning the escape-triggering path was never
    built and a clean result proves nothing. This is the case the guard was
    written for and it must keep failing.
    """
    home = _home_with_env(tmp_path, 'CIRIS_DATA_DIR="D:\\\\elsewhere\\\\data"\n')
    result = _run(home)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "derives from the home this job pinned" in result.stdout


def test_a_path_from_our_home_that_is_clean_passes(tmp_path: Path) -> None:
    """Written correctly (backslashes escaped), so it round-trips intact."""
    home = _home_with_env(tmp_path, "")
    escaped = str(home).replace("\\", "\\\\")
    (home / ".env").write_text(f'CIRIS_DATA_DIR="{escaped}/data"\n', encoding="utf-8")
    result = _run(home)
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_control_character_in_our_own_path_fails(tmp_path: Path) -> None:
    """The defect itself: an unescaped backslash-f reaching the value.

    Without this the suite would prove only that the guard can pass.
    """
    home = _home_with_env(tmp_path, "")
    # A LITERAL form feed in the value, which is what the corrupted path looks
    # like once it has been un-escaped and written back.
    #
    # Not a `\f` escape sequence: this project's own loader
    # (ciris_engine.logic.config.env_utils) does NOT process escapes — it returns
    # the backslash verbatim — so an escape sequence would pass the guard's
    # config-layer check here even though python-dotenv, which does unescape,
    # is where the original corruption came from. The raw-line check is the half
    # that fires on either platform, so that is the half this control exercises.
    (home / ".env").write_text(f'CIRIS_DATA_DIR="{home}/da\x0cta"\n', encoding="utf-8")
    result = _run(home)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "control character" in result.stdout.lower()


@pytest.mark.parametrize("missing", ["no-such-home"])
def test_a_missing_env_is_not_silently_green(tmp_path: Path, missing: str) -> None:
    """No .env at all must not read as 'nothing wrong'."""
    result = _run(tmp_path / missing)
    assert result.returncode != 0 or "no path values" not in result.stdout
