"""The published results page must PARSE. A syntax error blanks the whole page.

`docs/results/index.html` is the public evidence surface (cirisai.github.io).
Its behaviour lives in one inline <script>, and JavaScript aborts the ENTIRE
script on a parse error — not the offending statement, the whole block. So a
one-line mistake anywhere in it takes down every tab at once while the HTML
still renders, the server still returns 200, and every pane sits at whatever
placeholder text it shipped with.

That is exactly what happened. Adding the questions/rubrics tab introduced a
second `const esc=...` alongside the one already declared at line 223:

    SyntaxError: Identifier 'esc' has already been declared

Duplicate `const` at the same scope is a parse error, so the page went out with
its script dead. Every check that could plausibly have caught it passed: the
page returned 200, the deployed bytes matched the repo exactly, and
`data/batteries/index.json` and `en.json` both served 200. Nothing looked at
whether the code could run, and the symptom — panes reading "loading…" — looks
like a failed fetch, which sends you to inspect the data that is fine.

Two checks, deliberately overlapping:

  1. `node --check`, the real parser, when node is available.
  2. A duplicate top-level `const`/`let` scan in pure Python, which always runs.

The second exists because a gate that silently skips when a tool is missing is
the same as no gate on the machine that lacks it — and this defect's whole
character was passing every check that did run.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[2] / "docs" / "results" / "index.html"

#: `const x=`, `let x=` at column 0 — i.e. top level of the script block.
#: Anchored to line start on purpose: an indented declaration is inside a
#: function or block and may legitimately shadow an outer name.
TOP_LEVEL_DECL = re.compile(r"^(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=", re.M)


def _script() -> str:
    html = PAGE.read_text(encoding="utf-8")
    blocks = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
    assert blocks, "no <script> block in the results page — the page is all behaviour"
    return "\n".join(blocks)


def test_no_duplicate_top_level_declarations() -> None:
    """The exact defect: two `const esc=` in one scope, which kills the script."""
    counts = Counter(TOP_LEVEL_DECL.findall(_script()))
    dupes = {name: n for name, n in counts.items() if n > 1}
    assert not dupes, (
        f"top-level identifiers declared more than once: {dupes}. "
        "A duplicate const/let at the same scope is a SyntaxError, and JS aborts "
        "the WHOLE script — every tab on the page goes blank while the HTML still "
        "renders and the server still returns 200. Reuse the existing declaration."
    )


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_script_parses_under_a_real_javascript_parser(tmp_path: Path) -> None:
    """`node --check` catches everything the regex above cannot.

    The scan is a targeted guard against one known mistake; this is the general
    one. Both are kept because CI has node and some dev machines do not.
    """
    js = tmp_path / "page.js"
    js.write_text(_script(), encoding="utf-8")
    proc = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
    assert proc.returncode == 0, (
        "docs/results/index.html's script does not parse, so the published page "
        f"will render with NO behaviour at all:\n{proc.stderr.strip()}"
    )
