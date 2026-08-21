"""The substrate is the only verify in the tree (CIRISAgent#917, 2.9.29).

The standalone ``ciris-verify`` pin was dropped from requirements.txt once the
producer's last genuine consumer — ``jcs_canonicalize`` — was rewired onto the
ciris-server wheel's folded verify FFI. Nothing in the tree may import the
standalone package at load time any more.

This is a *ratchet*, not a smoke test. The pin has been dropped once before
(680c4551f) BEFORE its precondition was met, and CI only caught it as
``ModuleNotFoundError`` in six shards of PR #890 — because the dev machine
still had the wheel installed from an earlier bump. These tests fail on the
developer's machine too, where the standalone package is usually present.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCANNED = ("ciris_engine", "ciris_adapters", "tools")


def _hard_imports(path: Path) -> list[tuple[int, str]]:
    """Top-level-resolvable imports of the standalone package in one file.

    Docstrings and comments are invisible to ``ast`` — which is the point. The
    2026-07-16 pin-restore comment named six "blocking" imports; four of them
    were docstring prose and one was a stale comment. Parsing, not grepping,
    is what told the truth.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - defensive
        return []

    # client.py's loader keeps a guarded `import ciris_verify` to find a
    # legacy standalone .so; it is wrapped in try/except ImportError and is
    # allowed to fail. Collect those so they can be excused.
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            handled = any(
                (h.type is None)
                or (isinstance(h.type, ast.Name) and h.type.id in ("ImportError", "Exception"))
                or (isinstance(h.type, ast.Tuple)
                    and any(isinstance(e, ast.Name) and e.id in ("ImportError", "Exception")
                            for e in h.type.elts))
                for h in node.handlers
            )
            if handled:
                for child in ast.walk(node):
                    guarded.add(getattr(child, "lineno", -1))

    found = []
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.ImportFrom):
            name = node.module
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "ciris_verify" or a.name.startswith("ciris_verify."):
                    name = a.name
                    break
        if name and (name == "ciris_verify" or name.startswith("ciris_verify.")):
            if node.lineno not in guarded:
                found.append((node.lineno, name))
    return found


class TestNoStandaloneVerifyImports:
    def test_no_unguarded_standalone_import_in_tree(self) -> None:
        offenders = []
        for pkg in SCANNED:
            for py in (REPO / pkg).rglob("*.py"):
                for lineno, mod in _hard_imports(py):
                    offenders.append(f"{py.relative_to(REPO)}:{lineno} imports {mod!r}")

        assert not offenders, (
            "The `ciris-verify` pin was dropped in 2.9.29 (#917); the substrate's folded "
            "verify FFI is the only verify in the tree. These unguarded imports would raise "
            "ModuleNotFoundError in a fresh environment:\n  "
            + "\n  ".join(offenders)
            + "\n\nRewire to `from ciris_adapters.ciris_verify.ffi_bindings import ...`, or wrap "
              "in try/except ImportError if the capability is genuinely optional."
        )

    def test_requirements_does_not_pin_standalone_verify(self) -> None:
        for i, line in enumerate((REPO / "requirements.txt").read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            assert not stripped.split(";")[0].strip().lower().startswith("ciris-verify"), (
                f"requirements.txt:{i} re-pins ciris-verify: {stripped!r}. The substrate wheel "
                "carries all 88 ciris_verify_* C symbols; re-pinning reintroduces the version "
                "skew the JCS cutover eliminated by construction."
            )


class TestCanonicalizerRidesTheSubstrate:
    def test_substrate_so_is_searched_first(self) -> None:
        import ciris_server

        from ciris_adapters.ciris_verify.ffi_bindings._jcs import _candidate_paths

        assert _candidate_paths()[0] == str(ciris_server.verify_ffi_path()), (
            "The substrate's .so must be candidate #0. If the standalone wheel is searched "
            "first, the producer can silently canonicalize with a DIFFERENT verify than the "
            "Rust verifiers recompute with — the exact skew #917 closed."
        )

    def test_upstream_bumps_cannot_clobber_the_loader_patch(self) -> None:
        """_jcs.py must stay agent-managed.

        The upstream copy searches the standalone wheel ONLY. Re-vendoring it on a
        `ciris-verify` bump would restore a hard dependency at the signing path
        without touching requirements.txt — invisible to the tests above.
        """
        src = (REPO / "tools" / "update_ciris_verify.py").read_text()
        line = next((l for l in src.splitlines() if "AGENT_MANAGED = {" in l), "")
        assert "_jcs.py" in line, (
            "update_ciris_verify.py::AGENT_MANAGED no longer protects _jcs.py; the next "
            f"verify bump will overwrite the substrate-first loader. Found: {line.strip()!r}"
        )

    @pytest.mark.parametrize(
        "value,expected",
        [
            ({"b": 1, "a": 2}, b'{"a":2,"b":1}'),
            # ensure_ascii=True was the pre-cutover bug: it emitted \uXXXX escapes
            # that the Rust verifier never reproduces.
            ({"k": "café ☕"}, b'{"k":"caf\xc3\xa9 \xe2\x98\x95"}'),
            ({"n": 1.0, "e": 1e30}, b'{"e":1e+30,"n":1}'),
            ({}, b"{}"),
        ],
    )
    def test_rfc8785_conformance(self, value: object, expected: bytes) -> None:
        from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize

        assert jcs_canonicalize(value) == expected


class TestFreshEnvironment:
    def test_producer_path_works_with_standalone_absent(self) -> None:
        """End-to-end in a subprocess where `ciris_verify` cannot be imported.

        A meta_path blocker reproduces the fresh-CI condition on a dev box that
        still has the wheel installed — the blind spot that let 680c4551f ship.
        """
        script = """
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "ciris_verify" or fullname.startswith("ciris_verify."):
            raise ImportError("SIMULATED: standalone ciris-verify not installed")
        return None
sys.meta_path.insert(0, Block())
for m in [k for k in list(sys.modules) if k == "ciris_verify" or k.startswith("ciris_verify.")]:
    del sys.modules[m]

from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize
assert jcs_canonicalize({"b": 1, "a": 2}) == b'{"a":2,"b":1}'

from ciris_engine.logic.services.infrastructure.authentication.attestation import tree_verify
assert tree_verify._load_verify_ffi_lib() is not None, "tree_verify lost its FFI"

from ciris_adapters.ciris_verify.ffi_bindings import (
    CIRISVerify, LicenseStatus, setup_logging, AttestationInProgressError,
)
print("OK")
"""
        proc = subprocess.run(
            [sys.executable, "-c", script], cwd=REPO, capture_output=True, text=True, timeout=300
        )
        assert proc.returncode == 0 and "OK" in proc.stdout, (
            "The tree still needs the standalone ciris-verify wheel.\n"
            f"stdout: {proc.stdout[-2000:]}\nstderr: {proc.stderr[-2000:]}"
        )
