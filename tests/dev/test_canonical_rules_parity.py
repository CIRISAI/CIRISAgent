"""Drift protection: tree_verify's inlined canonical rules MUST equal stage_runtime's.

`tools.dev.stage_runtime.ExemptRules` is the build-time source of truth for
what gets staged into the canonical runtime tree. The runtime verifier
(`ciris_engine/.../tree_verify.py`) inlines the same rules — it can't import
from ``tools/`` because ``tools/`` doesn't ship to production runtimes (Docker
runtime, mobile bundles, wheel install). If those two definitions drift,
``verify_tree()`` walks a different file set than what was signed at CI time
and L4 attestation silently breaks.

This test pins them together. Edit BOTH at once or fix the drift here.
"""
from __future__ import annotations

from ciris_engine.logic.services.infrastructure.authentication.attestation.tree_verify import (
    _CANONICAL_EXEMPT_DIRS,
    _CANONICAL_EXEMPT_EXTENSIONS,
    _CANONICAL_INCLUDE_ROOTS,
)
from tools.dev.stage_runtime import CANONICAL_RULES


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
