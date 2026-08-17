"""Files we read as text must declare utf-8, or Windows reads them as cp1252.

THE BUG, found in a Windows CI log -- a log file that only existed because the
symlink fallback landed in the same release:

    Failed to load prompts from ...\\ciris_engine\\logic\\dma\\prompts\\action_selection_pdma.yml:
    'charmap' codec can't decode byte 0x8f in position 7288: character maps to <undefined>

`open(path, "r")` with no encoding uses `locale.getpreferredencoding()`. On
Linux and macOS that is UTF-8, so nobody notices. On Windows it is cp1252, which
cannot represent most of what our content files contain.

WHY IT IS WORSE THAN A CRASH. The DMA loader catches the exception and logs a
WARNING, so the agent came up, fell back to default prompts, and kept running --
reasoning with different prompts than every other platform, with no failure
anyone would chase. A crash gets fixed. A warning in a log nobody can find does
not, and until this release Windows had no `incidents_latest.log` at all.

SCOPE. This asserts the property for files that DO carry non-ASCII: prompts,
localization, ACCORD text, manifests, templates, and .env. The wider codebase
still has text opens without an explicit encoding; they are being fixed as they
are touched rather than in one sweeping rewrite, and this test guards the paths
that are known to break rather than pretending to cover everything.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]

#: Files whose CONTENT is known to contain non-ASCII, or that carry user paths.
_RISKY_CONTEXT = re.compile(
    r"prompt|localiz|accord|guide|template|\.yml|\.yaml|\.md|\.txt|\.json|manifest|identity|locale",
    re.I,
)

ROOTS = ["ciris_engine", "ciris_adapters"]


def _unencoded_text_opens(path: pathlib.Path) -> list[tuple[int, str]]:
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    lines = src.split("\n")
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "open":
            name = "open"
        elif isinstance(fn, ast.Attribute) and fn.attr in ("open", "read_text", "write_text"):
            name = fn.attr
        else:
            continue

        if any(k.arg == "encoding" for k in node.keywords):
            continue

        # Binary mode has no encoding, by definition.
        mode = ""
        if name == "open" and len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = str(node.args[1].value)
        for k in node.keywords:
            if k.arg == "mode" and isinstance(k.value, ast.Constant):
                mode = str(k.value.value)
        if "b" in mode:
            continue

        context = "\n".join(lines[max(0, node.lineno - 4) : node.lineno])
        if _RISKY_CONTEXT.search(context):
            found.append((node.lineno, lines[node.lineno - 1].strip()[:100]))
    return found


@pytest.mark.parametrize("root", ROOTS)
def test_content_bearing_files_are_opened_as_utf8(root: str) -> None:
    """The assertion that would have caught the DMA prompt failure on Linux."""
    failures = []
    for path in (REPO / root).rglob("*.py"):
        for lineno, snippet in _unencoded_text_opens(path):
            failures.append(f"{path.relative_to(REPO)}:{lineno}  {snippet}")

    assert not failures, (
        f"{len(failures)} text open(s) of a content-bearing file without encoding='utf-8'. "
        "On Windows the locale default is cp1252 and these raise UnicodeDecodeError -- which the "
        "DMA loader swallows as a WARNING, so the agent silently runs on fallback prompts.\n  "
        + "\n  ".join(failures)
    )


def test_the_dma_prompt_loader_specifically() -> None:
    """Name the exact site that broke, so a regression is unambiguous."""
    text = (REPO / "ciris_engine/logic/dma/base_dma.py").read_text(encoding="utf-8")
    assert 'open(prompt_file, "r", encoding="utf-8")' in text, (
        "base_dma.py no longer opens the prompt YAML as utf-8; on Windows this fails with "
        "'charmap' codec can't decode byte 0x8f and the agent falls back to default prompts"
    )


def test_the_prompt_file_really_does_contain_non_ascii() -> None:
    """Prove the hazard rather than assuming it.

    If this file were pure ASCII the fix would be precautionary; it is not, and
    position 7288 in the Windows error is a real byte in a real file.
    """
    p = REPO / "ciris_engine/logic/dma/prompts/action_selection_pdma.yml"
    if not p.exists():
        pytest.skip("prompt file not in this checkout")
    raw = p.read_bytes()
    non_ascii = [b for b in raw if b > 127]
    assert non_ascii, "action_selection_pdma.yml is pure ASCII; the cp1252 hazard would not apply"

    # And that decoding it as cp1252 genuinely fails, which is what Windows did.
    with pytest.raises(UnicodeDecodeError):
        raw.decode("cp1252")
