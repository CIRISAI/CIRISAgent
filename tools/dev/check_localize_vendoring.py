#!/usr/bin/env python3
"""Is the vendored CIRISClient localization pipeline the state it claims to be?

    python3 tools/dev/check_localize_vendoring.py                 # check (CI, pre-commit)
    python3 tools/dev/check_localize_vendoring.py --print         # digests as they are now
    python3 tools/dev/check_localize_vendoring.py --upstream ~/CIRISClient [--ref origin/main]
                                                                  # what moved upstream since
    python3 tools/dev/check_localize_vendoring.py --revendor ~/CIRISClient --ref origin/main
                                                                  # pull the verbatim files, re-record

Mirrors CIRISClient's ``packaging/check_vendoring.py``: per-file digests, not a
set of names, so a DECLARED file that changes without the record changing is a
failure rather than a silent middle. The record is ``localization/vendored.json``
(the human-readable account is ``localization/VENDORED.md``).

Three kinds of entry:

``verbatim``  byte-identical to upstream at the recorded commit. The file's
              sha256 must equal the recorded upstream sha256. An edit here is a
              fork, and a fork has to be declared, not discovered.
``patched``   upstream plus a declared patch (``patch`` names the diff in the
              tree). The file must equal the recorded ``sha256`` of the patched
              result, and the upstream digest stays recorded beside it.
``derived``   adapted for this repo (the lane workflows). Provenance only: the
              upstream digest is recorded so ``--upstream`` can say when the
              source moved, but the file is ours and is not drift-checked.

Also: every file under a directory the record OWNS (``owned_dirs``) must be
declared. A glossary that appears without a re-vendor is a file nobody can
trace.

Stdlib + git only. The default check is offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
RECORD = Path("localization") / "vendored.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_record(root: Path) -> Dict[str, Any]:
    path = root / RECORD
    if not path.is_file():
        raise SystemExit(f"[FAIL] no vendoring record at {path}")
    record: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return record


def check(root: Path) -> List[str]:
    """Every problem with the vendored tree under ``root``. Empty = clean."""
    record = load_record(root)
    problems: List[str] = []
    declared = set()
    entries: List[Dict[str, Any]] = record.get("files", [])
    if not entries:
        problems.append("the record declares no files -- a check over nothing is not a check")
    for entry in entries:
        rel = entry["path"]
        declared.add(rel)
        kind = entry.get("kind", "verbatim")
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: declared {kind} but missing")
            continue
        digest = sha256(path.read_bytes())
        if kind == "verbatim":
            if digest != entry["upstream_sha256"]:
                problems.append(
                    f"{rel}: differs from upstream {entry['upstream_path']} @ "
                    f"{record['upstream']['commit'][:12]} (sha256 {digest[:12]} != "
                    f"{entry['upstream_sha256'][:12]}). Re-vendor it, or declare the edit "
                    f"as a patch in {RECORD}."
                )
        elif kind == "patched":
            patch = entry.get("patch")
            if not patch or not (root / patch).is_file():
                problems.append(f"{rel}: declared patched but its patch file {patch!r} is missing")
            if digest != entry.get("sha256"):
                problems.append(
                    f"{rel}: differs from its recorded patched state (sha256 {digest[:12]} != "
                    f"{str(entry.get('sha256'))[:12]}). Update the patch and the record together."
                )
        elif kind == "derived":
            if not entry.get("upstream_sha256"):
                problems.append(f"{rel}: derived entry records no upstream digest")
        else:
            problems.append(f"{rel}: unknown entry kind {kind!r}")
    for owned in record.get("owned_dirs", []):
        base = root / owned
        if not base.is_dir():
            problems.append(f"{owned}: owned directory is missing")
            continue
        for path in sorted(p for p in base.rglob("*") if p.is_file()):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in declared:
                problems.append(f"{rel}: undeclared file in vendored directory {owned}")
    return problems


def _git_show(checkout: Path, ref: str, path: str) -> Optional[bytes]:
    proc = subprocess.run(["git", "-C", str(checkout), "show", f"{ref}:{path}"], capture_output=True)
    return proc.stdout if proc.returncode == 0 else None


def _git_rev(checkout: Path, ref: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", ref], capture_output=True, text=True, check=True
    ).stdout
    return out.strip()


def upstream_moves(root: Path, checkout: Path, ref: str) -> List[str]:
    record = load_record(root)
    moved: List[str] = []
    for entry in record["files"]:
        data = _git_show(checkout, ref, entry["upstream_path"])
        if data is None:
            moved.append(f"{entry['upstream_path']}: gone upstream at {ref}")
        elif sha256(data) != entry["upstream_sha256"]:
            moved.append(f"{entry['upstream_path']}: changed upstream ({entry.get('kind', 'verbatim')})")
    return moved


def revendor(root: Path, checkout: Path, ref: str) -> int:
    record = load_record(root)
    patched = [e["path"] for e in record["files"] if e.get("kind") == "patched"]
    if patched:
        print("[refuse] patched entries must be re-applied by hand first: " + ", ".join(patched))
        return 1
    commit = _git_rev(checkout, ref)
    for entry in record["files"]:
        data = _git_show(checkout, ref, entry["upstream_path"])
        if data is None:
            print(f"[refuse] {entry['upstream_path']} does not exist at {ref}")
            return 1
        if entry.get("kind", "verbatim") == "verbatim":
            (root / entry["path"]).write_bytes(data)
        elif sha256(data) != entry["upstream_sha256"]:
            print(f"[derived] {entry['path']}: upstream moved -- merge {entry['upstream_path']} by hand")
        entry["upstream_sha256"] = sha256(data)
    record["upstream"]["commit"] = commit
    record["upstream"]["ref"] = ref
    (root / RECORD).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"re-vendored from {commit}; review the diff, then run the check")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--root", type=Path, default=REPO, help=argparse.SUPPRESS)
    ap.add_argument("--print", action="store_true", dest="print_digests")
    ap.add_argument("--upstream", type=Path, default=None, metavar="CHECKOUT")
    ap.add_argument("--revendor", type=Path, default=None, metavar="CHECKOUT")
    ap.add_argument("--ref", default="origin/main")
    args = ap.parse_args(argv)

    if args.print_digests:
        for entry in load_record(args.root)["files"]:
            path = args.root / entry["path"]
            digest = sha256(path.read_bytes()) if path.is_file() else "MISSING"
            print(f"{digest}  {entry['path']}")
        return 0
    if args.revendor is not None:
        return revendor(args.root, args.revendor, args.ref)
    if args.upstream is not None:
        moved = upstream_moves(args.root, args.upstream, args.ref)
        for m in moved:
            print(f"  {m}")
        print(f"{len(moved)} upstream change(s) since the recorded commit" if moved else "upstream unchanged")
        return 1 if moved else 0

    record = load_record(args.root)
    problems = check(args.root)
    print(f"  localize vendoring -- {len(record['files'])} file(s) from {record['upstream']['repo']}")
    print(f"    upstream commit : {record['upstream']['commit']}")
    if problems:
        for p in problems:
            print(f"[FAIL] {p}")
        return 1
    print("[OK] every vendored file matches its record")
    return 0


if __name__ == "__main__":
    sys.exit(main())
