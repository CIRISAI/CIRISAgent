"""Staged QA environment — runs QA against a venv installed from the canonical staged tree.

When QA runs against the dev tree, it validates "the source tree works."
That's necessary but not sufficient — a developer can edit a file that's
present in the dev tree but excluded from the wheel (e.g. anything outside
``ciris_engine`` / ``ciris_adapters`` / ``ciris_sdk``, or anything filtered
by ``setup.py``'s ``package_data``), and dev-tree QA will pass while the
shipped wheel is broken.

This module closes that gap. ``prepare()`` produces a ``StagedEnvironment``
backed by:

  1. The canonical staged runtime tree (``tools/dev/stage_runtime``)
  2. The build infrastructure copied alongside (setup.py, pyproject.toml,
     MANIFEST.in, requirements.txt, README.md, LICENSE) so pip can build
     a wheel from the staged tree
  3. A fresh venv with that wheel installed

Then ``APIServerManager`` swaps its server-launch command from
``[sys.executable, main.py]`` to ``[<venv>/bin/ciris-server]``. The QA
test code still runs from the dev tree, but the *server under test*
is the installed-from-staged-wheel artifact — exactly what users get.

Idempotent: by default the staged env lives at ``/tmp/ciris-staged-qa/``
and is reused across QA runs. Pass ``rebuild=True`` (or
``--rebuild-staged`` from the CLI) to force a clean rebuild — useful
after structural changes (adding/removing files in the runtime
packages, changing setup.py, bumping requirements).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tools.dev.stage_runtime import stage_runtime

logger = logging.getLogger(__name__)

DEFAULT_STAGED_ROOT = Path("/tmp/ciris-staged-qa")

BUILD_INFRASTRUCTURE_FILES = (
    "setup.py",
    "pyproject.toml",
    "MANIFEST.in",
    "requirements.txt",
    "README.md",
    "LICENSE",
)


@dataclass(frozen=True)
class StagedEnvironment:
    """Paths to a prepared staged QA environment."""

    root: Path
    """Top-level dir holding everything (tree + venv + wheel)."""

    tree: Path
    """The canonical staged source tree + build infrastructure (where pip builds from)."""

    venv: Path
    """The venv with the wheel installed."""

    wheel: Path
    """The built wheel file (under tree/dist/)."""

    total_hash: str
    """Canonical sha256 of the staged tree (matches CIRISVerify file_tree_hash)."""

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    @property
    def ciris_server(self) -> Path:
        return self.venv / "bin" / "ciris-server"


def _copy_build_infra(src: Path, dest: Path) -> None:
    """Copy the files pip needs to build a wheel into the staged tree."""
    for fname in BUILD_INFRASTRUCTURE_FILES:
        src_file = src / fname
        if not src_file.exists():
            logger.warning(
                "build infra file missing: %s — wheel build may fail", src_file
            )
            continue
        shutil.copy2(src_file, dest / fname)


def _build_wheel(tree: Path) -> Path:
    """Run ``python -m build --wheel`` in the tree dir and return the wheel path.

    Builds in an isolated env (per pyproject.toml's ``[build-system] requires``)
    so the wheel build doesn't depend on whichever setuptools/wheel happens
    to be installed in the ambient Python — matters in CI runners that ship
    pip+wheel but not setuptools.
    """
    logger.info("building wheel from staged tree: %s", tree)
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel"],
        cwd=tree,
        check=True,
    )
    dist = tree / "dist"
    wheels = sorted(dist.glob("ciris_agent-*.whl"))
    if not wheels:
        raise RuntimeError(f"no wheel produced under {dist}")
    return wheels[-1]  # the most recently built (highest version-sort)


def _create_venv(venv_path: Path, wheel: Path) -> None:
    """Create a venv and install the wheel + dev deps for QA into it."""
    logger.info("creating venv at %s", venv_path)
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
    pip = venv_path / "bin" / "pip"
    subprocess.run([str(pip), "install", "--upgrade", "pip", "wheel"], check=True)
    logger.info("installing wheel into venv: %s", wheel.name)
    subprocess.run([str(pip), "install", str(wheel)], check=True)


def prepare(
    src: Path,
    root: Path = DEFAULT_STAGED_ROOT,
    rebuild: bool = False,
) -> StagedEnvironment:
    """Stage the runtime tree, build a wheel from it, install into a venv.

    Idempotent when ``rebuild=False`` and the staged env already exists at
    ``root`` — reuses the existing venv + wheel, only re-stages if the
    canonical hash of the source tree differs from the staged tree's
    recorded hash.

    Args:
        src: Source repo root.
        root: Top-level dir for the staged env (default ``/tmp/ciris-staged-qa``).
        rebuild: If True, blow away ``root`` and start fresh.

    Returns:
        A ``StagedEnvironment`` describing the prepared dirs/binaries.
    """
    src = src.resolve()
    root = root.resolve()

    if src == root or root.is_relative_to(src):
        raise ValueError(f"refusing to stage into source tree (src={src}, root={root})")

    tree = root / "tree"
    venv = root / "venv"
    hash_file = root / "tree.hash"

    # Compute fresh staging hash without yet writing anything (used for the
    # idempotence check).
    fresh_hash: Optional[str] = None

    needs_full_rebuild = (
        rebuild
        or not root.exists()
        or not tree.exists()
        or not venv.exists()
        or not hash_file.exists()
    )

    if not needs_full_rebuild:
        # Compute the source-tree's canonical hash and compare. If they
        # match, the existing staged env is still valid — short-circuit.
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ciris-stage-cmp-") as tmp:
            fresh = stage_runtime(src, Path(tmp))
            fresh_hash = fresh["total_hash"]
        recorded = hash_file.read_text().strip()
        if recorded == fresh_hash:
            wheels = sorted((tree / "dist").glob("ciris_agent-*.whl"))
            if wheels:
                logger.info(
                    "reusing staged env at %s (hash %s)", root, fresh_hash[:24]
                )
                return StagedEnvironment(
                    root=root,
                    tree=tree,
                    venv=venv,
                    wheel=wheels[-1],
                    total_hash=fresh_hash,
                )
            logger.info("staged env exists but no wheel found — rebuilding")
            needs_full_rebuild = True
        else:
            logger.info(
                "staged tree hash drift (%s → %s) — rebuilding",
                recorded[:24],
                fresh_hash[:24],
            )
            needs_full_rebuild = True

    if root.exists():
        logger.info("removing previous staged env at %s", root)
        shutil.rmtree(root)
    root.mkdir(parents=True)

    logger.info("staging canonical runtime tree → %s", tree)
    result = stage_runtime(src, tree)
    total_hash = result["total_hash"]
    logger.info(
        "staged %d files (%d bytes) hash=%s",
        result["files_copied"],
        result["total_size"],
        total_hash[:24],
    )

    _copy_build_infra(src, tree)
    wheel = _build_wheel(tree)
    _create_venv(venv, wheel)
    hash_file.write_text(total_hash + "\n")

    return StagedEnvironment(
        root=root,
        tree=tree,
        venv=venv,
        wheel=wheel,
        total_hash=total_hash,
    )


def main() -> int:
    """CLI entry: ``python -m tools.qa_runner.staged_env [--rebuild] [--root PATH]``.

    Useful for prepping the staged env outside of a QA run, e.g. when
    iterating on the staging algorithm itself or when warming a CI cache.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--src",
        type=Path,
        default=Path.cwd(),
        help="Source repo root (default: cwd)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_STAGED_ROOT,
        help=f"Staged env root (default: {DEFAULT_STAGED_ROOT})",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Force a clean rebuild even if the staged env already exists",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    env = prepare(args.src, args.root, rebuild=args.rebuild)
    print(f"Staged env ready at: {env.root}")
    print(f"  tree:         {env.tree}")
    print(f"  venv:         {env.venv}")
    print(f"  wheel:        {env.wheel.name}")
    print(f"  total_hash:   {env.total_hash}")
    print(f"  ciris-server: {env.ciris_server}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
