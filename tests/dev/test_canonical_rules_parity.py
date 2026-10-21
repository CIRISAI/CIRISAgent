"""Drift protection: stage_runtime → tree_verify → build.yml sign flags MUST agree.

Three places encode the canonical inclusion/exclusion rules:
  1. ``tools/dev/stage_runtime.py::ExemptRules`` — what gets staged at build time
  2. ``ciris_engine/.../tree_verify.py`` (inlined tuples) — what verify_tree
     walks at runtime
  3. ``.github/workflows/build.yml`` ``ciris-build-sign sign --target python-source-tree``
     flags — what gets registered in the manifest

If ANY of those three drift apart, the wheel install walks a different file
set than what got registered, and L4 silently caps at 3 with `extra` /
`missing` failures — the bug class CIRISAgent#742 closed.

This test pins all three together. Edit one, fix the others, or this fails.
"""
from __future__ import annotations

import re
from pathlib import Path

from ciris_engine.logic.services.infrastructure.authentication.attestation.tree_verify import (
    _CANONICAL_EXEMPT_DIRS,
    _CANONICAL_EXEMPT_EXTENSIONS,
    _CANONICAL_INCLUDE_ROOTS,
)
from tools.dev.stage_runtime import CANONICAL_RULES


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_include_roots_match() -> None:
    assert tuple(CANONICAL_RULES.include_roots) == _CANONICAL_INCLUDE_ROOTS, (
        "tree_verify._CANONICAL_INCLUDE_ROOTS drifted from stage_runtime.CANONICAL_RULES.include_roots — "
        "update the inlined tuple in tree_verify.py to match."
    )


def test_exempt_dirs_match() -> None:
    assert tuple(CANONICAL_RULES.exempt_dirs) == _CANONICAL_EXEMPT_DIRS, (
        "tree_verify._CANONICAL_EXEMPT_DIRS drifted from stage_runtime.CANONICAL_RULES.exempt_dirs — "
        "update the inlined tuple in tree_verify.py to match."
    )


def test_exempt_extensions_match() -> None:
    assert tuple(CANONICAL_RULES.exempt_extensions) == _CANONICAL_EXEMPT_EXTENSIONS, (
        "tree_verify._CANONICAL_EXEMPT_EXTENSIONS drifted from stage_runtime.CANONICAL_RULES.exempt_extensions — "
        "update the inlined tuple in tree_verify.py to match."
    )


def _extract_sign_flags_for_target(target: str) -> dict:
    """Pull --tree-include / --tree-exempt-* values from the python-source-tree
    sign step in build.yml. Tolerates YAML continuation lines."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "build.yml").read_text()

    # Find the ciris-build-sign block whose --target value matches.
    # A 'block' here is the run-step body: from `ciris-build-sign sign \` to
    # the next `--output ...`.
    pattern = re.compile(
        r"ciris-build-sign sign \\\s*\n((?:.*\\\s*\n)+?\s*--output\s+\S+)",
        re.MULTILINE,
    )
    for match in pattern.finditer(workflow):
        block = match.group(1)
        if f"--target {target}" not in block:
            continue
        flags: dict = {"include": [], "exempt-dir": [], "exempt-ext": []}
        for key in ("include", "exempt-dir", "exempt-ext"):
            m = re.search(rf"--tree-{key}\s+([^\\]+?)\\", block)
            if m:
                flags[key] = m.group(1).split()
        return flags
    raise AssertionError(f"No ciris-build-sign sign block found for --target {target} in build.yml")


def test_build_yml_python_source_tree_sign_matches_canonical_rules() -> None:
    """The CI sign step's --tree-* flags must match stage_runtime.ExemptRules.

    Without this, ciris-build-sign falls back to its internal defaults (which
    exclude .json + other non-py extensions), and 30+ real runtime data files
    silently vanish from the registered manifest — CIRISAgent#742.
    """
    flags = _extract_sign_flags_for_target("python-source-tree")

    assert set(flags["include"]) == set(_CANONICAL_INCLUDE_ROOTS), (
        f"build.yml --tree-include = {flags['include']} differs from canonical "
        f"{list(_CANONICAL_INCLUDE_ROOTS)}. Update build.yml's python-source-tree sign step."
    )
    assert set(flags["exempt-dir"]) == set(_CANONICAL_EXEMPT_DIRS), (
        f"build.yml --tree-exempt-dir = {flags['exempt-dir']} differs from canonical "
        f"{list(_CANONICAL_EXEMPT_DIRS)}. Update build.yml's python-source-tree sign step."
    )
    assert set(flags["exempt-ext"]) == set(_CANONICAL_EXEMPT_EXTENSIONS), (
        f"build.yml --tree-exempt-ext = {flags['exempt-ext']} differs from canonical "
        f"{list(_CANONICAL_EXEMPT_EXTENSIONS)}. Update build.yml's python-source-tree sign step."
    )
