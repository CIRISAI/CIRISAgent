#!/usr/bin/env python3
"""check_evidence.py — resolve the CC evidence ``impl:`` manifest (CIRISAgent#911).

``evidence/cc_impl.tsv`` is the sibling spec-map manifest the Constitution's
``check_claims.py`` resolves cross-repo ``impl:CIRISAgent#911`` pointers against
(see CIRISConstitution ``constitution/EVIDENCE.md``). This is the CI gate that
keeps the manifest honest: every in-repo ``path#symbol`` MUST resolve to a symbol
that actually exists — a moved/renamed/deleted symbol is a build failure (a
spec-regression test), so a Constitution ``impl:`` pointer can never silently rot.

Manifest columns (TSV):  ``decimal_id  claim_id  repo  path#symbol  status``

Resolution:
  - ``repo=CIRISAgent`` -> resolve ``path#symbol`` in THIS repo. The file must
    exist and the symbol must be defined at module level (``def``/``class``/a
    module-level assignment) or as ``Class.method``. A dead pointer = FAIL.
  - ``repo=—``            -> ``open``/``normative-only`` row, no symbol; skipped.
  - ``status=staged``    -> the claim is spec-ahead; its row is still resolved if
    it carries a real ``path#symbol`` (a staged pointer that names a symbol must
    still resolve), but a staged row with no path (``—``) is informational.

Exit non-zero on any FAIL.
"""

from __future__ import annotations

import ast
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "evidence" / "cc_impl.tsv"
COLUMNS = ["decimal_id", "claim_id", "repo", "path#symbol", "status"]

# The status vocabulary defined by CIRISConstitution constitution/EVIDENCE.md.
# Validated here because an unrecognised status previously passed silently, which
# meant a typo ("impl " / "implemented") degraded a row to un-checked without
# failing anything — the same class of rot this gate exists to prevent.
KNOWN_STATUSES = {"impl", "staged", "substrate", "normative", "open"}

# `open` rows are acknowledged, tracked gaps. EVIDENCE.md gives them a `REPO#issue`
# pointer rather than a `path#symbol`, so they are shape-checked, not AST-resolved.
# Declaring a gap is the point: silence in this manifest reads as coverage.
_ISSUE_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*#\d+$")


def _module_symbols(tree: ast.Module) -> tuple[set[str], dict[str, set[str]]]:
    """Return (top-level names, {class_name: {method names}})."""
    top: set[str] = set()
    methods: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top.add(node.name)
        elif isinstance(node, ast.ClassDef):
            top.add(node.name)
            methods[node.name] = {
                m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    top.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            top.add(node.target.id)
    return top, methods


def resolve(pointer: str) -> str | None:
    """Return an error string if ``path#symbol`` does not resolve, else None."""
    if "#" not in pointer:
        return f"pointer has no '#symbol': {pointer!r}"
    path_str, symbol = pointer.split("#", 1)
    path = ROOT / path_str
    if not path.exists():
        return f"file does not exist: {path_str}"
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as e:  # pragma: no cover - would be a broken repo
        return f"could not parse {path_str}: {e}"
    top, methods = _module_symbols(tree)
    if "." in symbol:
        cls, meth = symbol.split(".", 1)
        if cls not in top:
            return f"class not found: {path_str}#{cls}"
        if meth not in methods.get(cls, set()):
            return f"method not found: {path_str}#{symbol}"
        return None
    if symbol not in top:
        return f"symbol not found: {path_str}#{symbol}"
    return None


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL: manifest missing: {MANIFEST}", file=sys.stderr)
        return 1
    errors: list[str] = []
    resolved = skipped = declared_open = 0
    with MANIFEST.open() as f:
        reader = csv.reader((ln for ln in f if not ln.startswith("#")), delimiter="\t")
        header = next(reader, None)
        if header != COLUMNS:
            print(f"FAIL: header {header} != {COLUMNS}", file=sys.stderr)
            return 1
        for ln, row in enumerate(reader, start=2):
            if not row or not any(c.strip() for c in row):
                continue
            if len(row) != len(COLUMNS):
                errors.append(f"L{ln}: expected {len(COLUMNS)} columns, got {len(row)}")
                continue
            _decimal, claim, repo, pointer, status = (c.strip() for c in row)

            if status not in KNOWN_STATUSES:
                errors.append(f"L{ln} [{claim}]: unknown status {status!r}; expected one of {sorted(KNOWN_STATUSES)}")
                continue

            # An `open` row declares a tracked gap and points at an issue, not a
            # symbol. Shape-check it so a gap cannot be "declared" against a
            # reference nobody can follow.
            if status == "open":
                if not _ISSUE_REF.match(pointer):
                    errors.append(
                        f"L{ln} [{claim}]: status=open needs a REPO#issue pointer "
                        f"(e.g. CIRISAgent#942), got {pointer!r}"
                    )
                else:
                    declared_open += 1
                continue

            if repo != "CIRISAgent" or pointer in ("", "—"):
                skipped += 1
                continue
            err = resolve(pointer)
            if err:
                errors.append(f"L{ln} [{claim}]: {err}")
            else:
                resolved += 1

    for e in errors:
        print(f"FAIL: {e}", file=sys.stderr)
    print(
        f"cc_impl.tsv: {resolved} in-repo pointers resolved, {declared_open} declared gaps, "
        f"{skipped} skipped, {len(errors)} failed"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
