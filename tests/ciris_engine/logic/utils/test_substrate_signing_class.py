"""No call site may choose a signing verb. The class, not the sixth instance.

`Engine.local_sign` cannot sign with a sealed classical key, and since
ciris-server 0.5.162 it says so permanently:

    RuntimeError: local_sign cannot sign with a SEALED classical key — this is
    permanent, not transient, and the signature was NOT produced

Every node with ONE federation identity (CIRISServer#380 / CIRISPersist#616)
holds its classical half in the sealed keystore. So this is not an edge case; it
is every production node.

The same defect appeared six times across four repositories, and **every instance
was locally right** — which is why it survived six reviews. One site even fell
back to `local_sign` only when no PQC signer was wired, which reads as careful
degradation right up until you know persist deleted the classical-only state.

So the invariant is not "call the right verb". It is: **no site chooses a verb.**
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: tests/ciris_engine/logic/utils/<this file> -> 4 levels up is the repo root.
#: This was parents[5] on the first draft, which resolved above the repo, so the
#: scan walked nothing and the ban below passed over an empty set. Zero findings
#: across an unchecked set is not a pass — `test_scan_actually_sees_the_tree`
#: exists so that mistake cannot be silent a second time.
REPO = pathlib.Path(__file__).resolve().parents[4]

#: Trees that talk to the substrate. Not `tests/` — a test may legitimately
#: exercise the raw verb (e.g. proving it still refuses a sealed key).
PRODUCTION_TREES = ["ciris_engine", "ciris_adapters", "ciris_sdk"]

#: The one module allowed to name the raw verbs.
SANCTIONED = "ciris_engine/logic/utils/substrate_signing.py"


def _py_files():
    for tree in PRODUCTION_TREES:
        root = REPO / tree
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def _attr_calls(path: pathlib.Path, name: str) -> list[int]:
    """Line numbers of `<anything>.name(...)` calls — AST, so comments and
    docstrings that merely mention the verb are not flagged."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == name
    ]


def test_scan_actually_sees_the_tree() -> None:
    """The bans below are only meaningful over a non-empty set.

    A path bug once made this whole file pass while walking nothing. An
    instrument that reports success for work it never performed is the exact
    defect class this file exists to eliminate; it does not get an exemption for
    being a test.
    """
    files = list(_py_files())
    assert len(files) > 500, f"expected to scan the production trees, saw {len(files)} files"
    assert (REPO / SANCTIONED).is_file(), f"{SANCTIONED} not found under REPO={REPO}"


def test_no_production_site_calls_local_sign() -> None:
    """The verb that cannot work on a sealed key must not be called anywhere."""
    offenders = []
    for p in _py_files():
        rel = p.relative_to(REPO).as_posix()
        if rel == SANCTIONED:
            continue
        for line in _attr_calls(p, "local_sign"):
            offenders.append(f"{rel}:{line}")
    assert not offenders, (
        "these call `local_sign`, which refuses a sealed classical key permanently "
        f"(the signature is NOT produced): {offenders}. Use "
        "`substrate_signing.sign_classical(engine, data)` — same 64 Ed25519 bytes."
    )


def test_hybrid_verb_is_called_in_exactly_one_place() -> None:
    """Even the correct verb gets one caller, or the class regrows.

    Six locally-right instances is what made the original defect survive. A
    second direct caller of `local_sign_hybrid` is the first step back to that.
    """
    callers = []
    for p in _py_files():
        rel = p.relative_to(REPO).as_posix()
        if _attr_calls(p, "local_sign_hybrid"):
            callers.append(rel)
    assert callers == [SANCTIONED], (
        f"`local_sign_hybrid` is called from {callers}; only {SANCTIONED} may name "
        "the raw signing verbs, so custody rules live in exactly one place"
    )


def test_helper_returns_the_classical_bytes_unchanged() -> None:
    """`sign_classical` must be a true drop-in: same bytes, same length.

    If it ever returned something else, every signature on the wire would change
    shape and existing proofs would stop verifying.
    """
    from ciris_engine.logic.utils import substrate_signing

    class _FakeEngine:
        def local_sign_hybrid(self, data: bytes) -> dict:
            return {"classical_sig": b"c" * 64, "pqc_sig": b"p" * 3309}

    assert substrate_signing.sign_classical(_FakeEngine(), b"x") == b"c" * 64


def test_missing_pqc_is_reported_as_none_not_an_exception() -> None:
    """Hybrid-pending is read off the RESULT, never caught from a second verb."""
    from ciris_engine.logic.utils import substrate_signing

    class _NoPqcEngine:
        def local_sign_hybrid(self, data: bytes) -> dict:
            return {"classical_sig": b"c" * 64, "pqc_sig": None}

    classical, pqc = substrate_signing.sign_hybrid(_NoPqcEngine(), b"x")
    assert classical == b"c" * 64
    assert pqc is None


def test_a_failed_signature_propagates() -> None:
    """A signature that was not produced must never be papered over.

    Silent degradation is the half of this defect that cost 71 hours: a caller
    that swallows the error writes an unsigned row that reads as signed.
    """
    from ciris_engine.logic.utils import substrate_signing

    class _SealedEngine:
        def local_sign_hybrid(self, data: bytes) -> dict:
            raise RuntimeError("sealed key, signature NOT produced")

    with pytest.raises(RuntimeError):
        substrate_signing.sign_classical(_SealedEngine(), b"x")
