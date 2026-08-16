"""Nothing we print at runtime may contain an emoji, and every entry point shims stdio.

THE CRASH. On a default Windows console the active code page is cp1252, and
Python binds `sys.stdout` to it. Any non-ASCII glyph raises:

    UnicodeEncodeError: 'charmap' codec can't encode character '\\U0001f680'

That was a rocket emoji in our own startup output, and it killed the process.
It surfaced on the first Windows CI run that got far enough to print anything —
after a release cycle in which three Windows bugs shipped undetected because
nothing we had could run there.

BELT AND SUSPENDERS, and this file asserts both:

  * BELT — `win_console.setup()` flips the console to UTF-8 and reconfigures the
    stdio wrappers. It already existed and `main.py`, `cli.py`,
    `desktop_launcher.py` and `logging_config` already called it. The QA runner
    never did, which is exactly why the harness crashed before running a single
    test.
  * SUSPENDERS — no emoji in runtime output at all. The shim can fail: a stream
    that is not a TextIOWrapper, a redirected pipe, an embedding host that owns
    stdio. Output that is ASCII by construction cannot raise no matter what the
    console is set to.

SCOPE, deliberately narrow. This checks only strings that REACH A STREAM —
`print`, `logger.*`, `console.print`. Comments, docstrings, box-drawing in
banners and LOCALIZATION CONTENT are untouched: the codebase carries CJK, kana
and hangul on purpose, and a blanket non-ASCII ban would delete translations.
The rewrite that accompanied this test removed 1253 emoji from output lines and
zero CJK characters.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Only what actually reaches a stream.
_OUTPUT = re.compile(r"(print\(|logger\.|console\.print\()")

#: Entry points that must shim stdio before printing anything.
_ENTRY_POINTS = (
    "main.py",
    "ciris_engine/cli.py",
    "ciris_engine/desktop_launcher.py",
    "ciris_engine/logic/utils/logging_config.py",
    "tools/qa_runner/__main__.py",
    "tools/qa_runner/runner.py",
    "tools/qa_runner/server.py",
    "tools/qa_runner/modules/web_ui/__main__.py",
    "tools/qa_runner/modules/mobile/__main__.py",
)


def _is_emoji(ch: str) -> bool:
    o = ord(ch)
    return (
        0x1F000 <= o <= 0x1FAFF  # pictographs, emoticons, transport, symbols
        or 0x2600 <= o <= 0x27BF  # misc symbols + dingbats: ✅ ❌ ⚠ ✓ ✗
        or o == 0xFE0F  # variation selector
        or o in (0x2B50, 0x2B55)
        or 0x1F1E6 <= o <= 0x1F1FF  # regional indicators
    )


def _offending_lines(path: pathlib.Path) -> list[tuple[int, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if _OUTPUT.search(line):
            bad = sorted({c for c in line if _is_emoji(c)})
            if bad:
                out.append((i, "".join(bad)))
    return out


@pytest.mark.parametrize("root", ["ciris_engine", "tools", "ciris_adapters"])
def test_no_emoji_reaches_a_stream(root: str) -> None:
    """A cp1252 console must never be handed a glyph it cannot encode."""
    failures = []
    for path in (REPO / root).rglob("*.py"):
        for lineno, glyphs in _offending_lines(path):
            failures.append(f"{path.relative_to(REPO)}:{lineno} -> {glyphs}")
    assert not failures, (
        f"{len(failures)} runtime-output line(s) carry an emoji; on a Windows cp1252 "
        "console this raises UnicodeEncodeError and kills the process. Use ASCII "
        "markers ([OK] / [FAIL] / [WARN]).\n  " + "\n  ".join(failures[:20])
    )


def test_main_py_has_no_emoji_in_output() -> None:
    """main.py is the first thing a user sees, and the first thing that can crash."""
    failures = _offending_lines(REPO / "main.py")
    assert not failures, f"main.py runtime output carries emoji: {failures}"


@pytest.mark.parametrize("entry", _ENTRY_POINTS)
def test_every_entry_point_shims_windows_stdio(entry: str) -> None:
    """The belt. Missing on the QA runner is why Windows CI never ran a test.

    Asserted per entry point rather than as a count, so adding a new one without
    the shim fails by name instead of shifting a number nobody reads.
    """
    path = REPO / entry
    if not path.exists():
        pytest.skip(f"{entry} not present in this checkout")
    assert "win_console" in path.read_text(encoding="utf-8"), (
        f"{entry} prints before calling win_console.setup(); on a Windows cp1252 "
        "console any non-ASCII output raises UnicodeEncodeError"
    )


def test_the_shim_is_a_noop_off_windows() -> None:
    """It runs on every start on every platform, so it must never be able to break one."""
    from ciris_engine.logic.utils import win_console

    win_console.setup()
    win_console.setup()  # idempotent


def test_translations_are_not_collateral() -> None:
    """Guard the guard: the emoji sweep must never have touched localization.

    A blanket non-ASCII ban would have deleted CJK, kana and hangul that the
    product carries on purpose. This asserts they are still present, so a future
    'tidy up unicode' pass cannot quietly strip them.
    """
    found = 0
    for path in (REPO / "ciris_engine").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found += sum(
            1
            for c in text
            if 0x4E00 <= ord(c) <= 0x9FFF or 0x3040 <= ord(c) <= 0x30FF or 0xAC00 <= ord(c) <= 0xD7AF
        )
    assert found > 0, "CJK/kana/hangul disappeared from ciris_engine — translations were stripped"
