#!/usr/bin/env python3
"""Stage the canonical runtime tree from the source repository.

Produces a clean directory tree containing ONLY files that are loaded at
runtime. The same staging output is the canonical input for:

  - CIRISVerify manifest signing
        ``ciris-build-sign sign --tree <staged> --target python-source-tree``
  - Wheel packaging (``python -m build --wheel`` against staged tree)
  - Mobile bundling (Android Chaquopy ZIP, iOS Resources)
  - CIRISVerify file_integrity verification at runtime
        (``agent_root`` walk produces the same hashes as the signing-time walk)
  - QA against installed-wheel state (run tests against a venv that
    installed the wheel built from this staged tree)

The staging algorithm mirrors CIRISVerify's
``ciris_verify_core::security::build_manifest::walk_file_tree`` +
``ExemptRules`` so the canonical total hash computed here equals the
``file_tree_hash`` CIRISVerify computes when verifying ``agent_root``.

Strip rules (canonical, mirrors CI's ``ciris-build-sign --tree-exempt-*``
flags in ``.github/workflows/build.yml`` plus ``md`` for post-2.8.5
devnote-isolation):

::

  include_roots:      ciris_engine, ciris_adapters, ciris_sdk
  exempt_dirs:        __pycache__, .venv, venv, node_modules, logs,
                      .pytest_cache, .mypy_cache, dist, build,
                      .ruff_cache, .coverage, .tox, .nox, .git
  exempt_extensions:  pyc, pyo, env, log, audit, db, sqlite, sqlite3, md

``md`` is in the exempt list as of 2.8.5. Load-bearing markdown content
has been migrated to ``.txt`` (CIRIS_COMPREHENSIVE_GUIDE_*, accord_*,
agent_experience). The rule going forward is unambiguous: every ``.md``
file is devnotes and must not be load-bearing at runtime.

Usage::

    # Stage the canonical runtime tree to a destination directory:
    python -m tools.dev.stage_runtime /tmp/ciris-staged

    # Print the canonical manifest hash without copying (for CI comparison):
    python -m tools.dev.stage_runtime --check

    # Stage to dest AND print manifest hash + JSON to stdout:
    python -m tools.dev.stage_runtime /tmp/ciris-staged --print-manifest

The ``--print-manifest`` output is CI-stable and can be diffed against
the canonical manifest registered with CIRISRegistry under
``project=ciris-agent``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, TypedDict


class StagingResult(TypedDict):
    """Return shape for ``stage_runtime`` and ``--check`` mode."""

    files_copied: int
    total_size: int
    total_hash: str
    files: Dict[str, str]


@dataclass(frozen=True)
class ExemptRules:
    """Mirrors ``ciris_verify_core::security::build_manifest::ExemptRules``.

    Serialized into the signed ``FileTreeExtras`` at sign time so the
    runtime walker reproduces the same inclusion logic deterministically.
    Defaults match the flags ``ciris-build-sign`` is invoked with in CI
    plus the ``md`` extension exempt added in 2.8.5.
    """

    include_roots: List[str] = field(
        default_factory=lambda: ["ciris_engine", "ciris_adapters", "ciris_sdk"]
    )
    exempt_dirs: List[str] = field(
        default_factory=lambda: [
            # Build / cache / VCS noise
            "__pycache__",
            ".venv",
            "venv",
            "node_modules",
            "logs",
            ".pytest_cache",
            ".mypy_cache",
            "dist",
            "build",
            ".ruff_cache",
            ".coverage",
            ".tox",
            ".nox",
            ".git",
            # Non-runtime: tests + examples ship as devnotes only.
            # Excluding them everywhere keeps Android/iOS/desktop bundles
            # byte-equal — historically Android stripped them but the others
            # didn't, which is exactly the kind of cross-platform drift the
            # canonical staging eliminates.
            "tests",
            "examples",
            # Platform-specific bolt-ons that aren't part of the Python
            # runtime. Both directories live UNDER ciris_engine but ship as
            # separate artifacts:
            #   - gui_static/ = Next.js export from CIRISGUI-Standalone,
            #     bundled into desktop fat wheels for the desktop GUI server
            #   - desktop_app/ = CIRIS Desktop UberJar, bundled into desktop
            #     fat wheels (the Kotlin Compose Multiplatform desktop app)
            # Mobile doesn't ship either; desktop has both. Excluding them
            # from canonical staging means the Python runtime hash is the
            # same across all platforms. The two desktop add-ons get their
            # own integrity story (separate sign target if/when needed).
            "gui_static",
            "desktop_app",
        ]
    )
    exempt_extensions: List[str] = field(
        default_factory=lambda: [
            # Build / runtime caches
            "pyc",
            "pyo",
            # Sensitive / runtime-data outputs (never source artifacts)
            "env",
            "log",
            "audit",
            "db",
            "sqlite",
            "sqlite3",
            # Devnotes (post-2.8.5 — load-bearing markdown migrated to .txt)
            "md",
            # Type-checker metadata (PEP 561) and static .pyi stubs — not loaded
            # at runtime, only consumed by mypy/pyright.
            "pyi",
            # Stale-deletion markers that occasionally land under a runtime
            # package directory (e.g. `*.py.deleted` from interrupted refactors).
            "deleted",
        ]
    )
    exempt_filenames: List[str] = field(
        default_factory=lambda: [
            # Dotfiles / metadata files where Path.suffix == "" (so the
            # extension-based rule above doesn't match). PEP 561 marker
            # `py.typed` is technically `.typed` extension but cleaner to
            # gate by filename. `.gitignore` is a build-tool dotfile that
            # occasionally lands under a runtime package dir.
            "py.typed",
            ".gitignore",
        ]
    )

    def is_exempt(self, rel_path: Path) -> bool:
        """Return True iff the path matches any exempt rule (or is outside an include_root)."""
        parts = rel_path.parts
        if not parts:
            return True
        if parts[0] not in self.include_roots:
            return True
        for seg in parts:
            if seg in self.exempt_dirs:
                return True
        if rel_path.name in self.exempt_filenames:
            return True
        ext = rel_path.suffix.lstrip(".").lower()
        if ext in self.exempt_extensions:
            return True
        return False


CANONICAL_RULES = ExemptRules()


def _compute_tree_hash(file_hashes: Dict[str, str]) -> str:
    """Canonical total hash matching ``FileTreeExtras::compute_tree_hash``.

    BTreeMap-canonical iteration over ``(path, sha256)`` pairs, accumulating
    ``"{path}:{sha256}\\n"`` segments into a single SHA-256.
    """
    hasher = hashlib.sha256()
    for path in sorted(file_hashes):
        hasher.update(path.encode("utf-8"))
        hasher.update(b":")
        hasher.update(file_hashes[path].encode("utf-8"))
        hasher.update(b"\n")
    return f"sha256:{hasher.hexdigest()}"


def stage_runtime(
    src: Path,
    dest: Path,
    rules: ExemptRules = CANONICAL_RULES,
) -> StagingResult:
    """Stage the canonical runtime tree from ``src`` to ``dest``.

    If ``dest`` exists, it is removed first. Caller is responsible for
    pointing ``dest`` at a safe location (a tempdir or staged-build dir,
    not the source tree itself).

    Returns a dict with:
      - ``files_copied``: int — number of files included
      - ``total_size``: int — sum of file sizes
      - ``total_hash``: str — canonical ``"sha256:<hex>"`` matching CIRISVerify
      - ``files``: dict — ``{relative_path: "sha256:<hex>"}`` per file
    """
    src = src.resolve()
    dest = dest.resolve()
    # Refuse to clobber the actual source — staging on top of src itself, or
    # into one of the include_roots whose contents we'd rmtree first. A
    # generic build dir under the repo (e.g., client/androidApp/build/python-src)
    # is fine — that's exactly where Gradle wants the staged Python tree for
    # Chaquopy bundling.
    if src == dest:
        raise ValueError(f"refusing to stage into source tree (src=dest={src})")
    for include_root in rules.include_roots:
        included = (src / include_root).resolve()
        if dest == included or dest.is_relative_to(included):
            raise ValueError(
                f"refusing to stage into a source include_root (dest={dest} is under {included})"
            )

    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    file_hashes: Dict[str, str] = {}
    total_size = 0

    for include_root in rules.include_roots:
        root_path = src / include_root
        if not root_path.is_dir():
            continue
        for f in sorted(root_path.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src)
            if rules.is_exempt(rel):
                continue
            rel_str = str(rel).replace("\\", "/")
            content = f.read_bytes()
            file_hash = f"sha256:{hashlib.sha256(content).hexdigest()}"
            file_hashes[rel_str] = file_hash
            total_size += len(content)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    return {
        "files_copied": len(file_hashes),
        "total_size": total_size,
        "total_hash": _compute_tree_hash(file_hashes),
        "files": file_hashes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage canonical runtime tree (matches CIRISVerify walk_file_tree).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage::")[1] if "Usage::" in __doc__ else "",
    )
    parser.add_argument(
        "dest",
        nargs="?",
        type=Path,
        help="Destination directory for the staged tree (deleted if exists)",
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path.cwd(),
        help="Source repo root (default: current working directory)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compute the canonical hash + report counts WITHOUT staging (uses a tempdir)",
    )
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="Also print the manifest as JSON to stdout (after the staging completes)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors + the final hash",
    )
    args = parser.parse_args()

    if args.check:
        with tempfile.TemporaryDirectory(prefix="ciris-stage-check-") as tmp:
            result = stage_runtime(args.src, Path(tmp))
        if not args.quiet:
            print(f"Source: {args.src.resolve()}")
            print(f"Files:  {result['files_copied']:,}")
            print(f"Size:   {result['total_size']:,} bytes")
        print(f"Hash:   {result['total_hash']}")
        return 0

    if not args.dest:
        parser.error("dest required (or pass --check for a dry-run)")

    result = stage_runtime(args.src, args.dest)
    # When --print-manifest, stdout is reserved for the JSON manifest so
    # `python -m tools.dev.stage_runtime DEST --print-manifest > manifest.json`
    # produces parseable JSON. Human-readable output goes to stderr in that
    # mode; otherwise stdout (preserving the non-manifest UX).
    summary_stream = sys.stderr if args.print_manifest else sys.stdout
    if not args.quiet:
        print(
            f"Staged {result['files_copied']:,} files ({result['total_size']:,} bytes) → {args.dest}",
            file=summary_stream,
        )
    print(f"Hash: {result['total_hash']}", file=summary_stream)

    if args.print_manifest:
        json.dump(
            {
                "files_copied": result["files_copied"],
                "total_size": result["total_size"],
                "total_hash": result["total_hash"],
                "files": result["files"],
            },
            sys.stdout,
            indent=2,
            sort_keys=True,
        )
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
