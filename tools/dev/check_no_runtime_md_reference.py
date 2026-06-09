#!/usr/bin/env python3
"""D27 gate: runtime code must not reference its own ``.md`` files.

Markdown files are exempt from the L4 attestation tree (CIRISVerify's
``tree_verify`` excludes the ``.md`` extension), so any runtime code path that
*emits or reads a ``.md`` as trusted state* sits outside the integrity boundary
— a provenance gap (D27). CIRISAgent#807. The live instance this gate was built
for (the keys-dir ``README.md`` written at boot) is already fixed to ``.txt``.

Detection rule
--------------
Flag any **bare ``.md`` path literal** in the runtime package — a string whose
*entire* value is a path/glob ending in ``.md`` (e.g. ``"README.md"``,
``"SKILL.md"``, ``".md"``, ``"*.md"``). This deliberately does NOT match:
  - docstrings / comments that *mention* an FSD ``.md`` in prose ("see FOO.md")
    — those are not a bare path, so ``re.fullmatch`` rejects them;
  - Pydantic ``Field(description="... SKILL.md ...")`` metadata — prose, rejected.
So no AST kwarg/docstring special-casing is needed; the path-shape match alone
separates real file references from prose.

Allowlist
---------
A small set of files legitimately handle the **external skill-package format**
or merely name a ``.md`` to *exclude* it — these are not the agent depending on
its own markdown as trusted state. New genuine ``.md`` I/O trips the gate and
must be reviewed into the allowlist with a justification.

Usage:  python tools/dev/check_no_runtime_md_reference.py
Exit:   0 = clean, 1 = a non-allowlisted runtime .md reference was found.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# Runtime package(s) the gate covers (the code that ships inside the attested
# tree). Tests/tools/docs are out of scope by construction.
RUNTIME_ROOTS = ("ciris_engine",)

# A whole-literal path or glob ending in .md.
_MD_PATH = re.compile(r"[\w./\\*-]*\.md", re.IGNORECASE)

# Files allowed to reference a .md literal, each with the reason it is NOT a
# self-trusted-state dependency. Paths are repo-relative.
ALLOWED: dict[str, str] = {
    # The external OpenClaw/ClawdBot skill-package format — third-party bundles,
    # not CIRIS's own runtime state.
    "ciris_engine/logic/services/skill_import/converter.py": "writes external SKILL.md package format",
    "ciris_engine/logic/services/skill_import/parser.py": "reads external SKILL.md package format",
    # Names a guide .md only to EXCLUDE it from template enumeration (skip-set
    # membership, not file I/O on a trusted .md).
    "ciris_engine/logic/adapters/api/routes/setup/helpers.py": "skip-set excludes a guide .md from templates",
    # Enumerates .md as a non-Python content extension to EXCLUDE from mobile
    # bundling — the exclusion list itself, not a runtime dependency on a .md.
    "ciris_engine/logic/utils/mobile_exclusions.py": "lists .md as a mobile-excluded extension",
}


def find_md_literals(path: Path) -> List[Tuple[int, str]]:
    """Return (lineno, literal) for every bare .md path literal in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _MD_PATH.fullmatch(node.value):
                hits.append((node.lineno, node.value))
    return hits


def main() -> int:
    violations: List[str] = []
    for root in RUNTIME_ROOTS:
        for py in (REPO_ROOT / root).rglob("*.py"):
            rel = py.relative_to(REPO_ROOT).as_posix()
            hits = find_md_literals(py)
            if not hits:
                continue
            if rel in ALLOWED:
                continue
            for lineno, literal in hits:
                violations.append(f"{rel}:{lineno}  references {literal!r}")

    print("🔎 D27 runtime .md-reference gate")
    if violations:
        print(f"\n❌ {len(violations)} runtime .md reference(s) outside the allowlist:\n")
        for v in violations:
            print(f"  • {v}")
        print(
            "\nRuntime code must not depend on its own .md (it is outside the L4 "
            "attestation tree). Emit/read .txt instead, or — if this is an external "
            "package format — add the file to ALLOWED in this script with a reason."
        )
        return 1

    allow = ", ".join(sorted(ALLOWED)) or "none"
    print(f"✅ no runtime .md references (allowlisted external-format handlers: {len(ALLOWED)})")
    print(f"   allowlist: {allow}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
