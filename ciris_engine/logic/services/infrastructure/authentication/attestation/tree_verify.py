"""Runtime tree verification via CIRISVerify v1.13+ ``verify_tree()`` (Algorithm A).

This is the desktop / server / docker path to L4 file integrity. It walks
``agent_root`` on disk and compares byte-for-byte against the registered
``file_manifest_json`` for ``(project="ciris-agent", binary_version=CIRIS_VERSION)``,
using the SAME canonical algorithm that ``ciris-build-sign sign --tree`` writes
into the registry. CIRISVerify#9 / CIRISAgent#740.

Mobile (Chaquopy) intentionally stays on Algorithm B (``python_hashes`` parameter
of ``run_attestation_sync``) — see ``hashes.py``. Algorithm B caps at L3 by
construction; Algorithm A reaches L4.

Rules reference: the python-source-tree CI sign step in ``.github/workflows/build.yml``
calls ``ciris-build-sign sign --tree /tmp/ciris-staged`` WITHOUT explicit
include/exempt flags, so CIRISVerify applies its internal defaults to a tree
that has already been pre-filtered by ``tools.dev.stage_runtime``. To match
that hash at runtime we walk ``agent_root`` with the SAME pre-filter rules
(equivalently: the union/superset of CIRISVerify's defaults and our extras).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_default_agent_version() -> Optional[str]:
    """Resolve the agent version for registry lookup (channel suffix stripped)."""
    try:
        from ciris_engine.constants import CIRIS_VERSION

        return CIRIS_VERSION.split("-")[0] if "-" in CIRIS_VERSION else CIRIS_VERSION
    except Exception:
        return None


def resolve_install_root() -> Optional[str]:
    """Resolve the directory that contains ``ciris_engine`` / ``ciris_adapters`` / ``ciris_sdk``.

    Order:
      1. ``CIRIS_AGENT_ROOT`` env var (explicit operator override)
      2. ``CIRIS_HOME`` env var (docker convention — runtime stage sets ``/app``)
      3. Package-relative — parent of ``ciris_engine.__file__``'s package dir
         (works for any pip install: site-packages, editable, wheel-into-venv)

    Returns:
        Absolute path string, or ``None`` if no resolution succeeded.
    """
    explicit = os.environ.get("CIRIS_AGENT_ROOT")
    if explicit:
        return explicit

    home = os.environ.get("CIRIS_HOME")
    if home and (Path(home) / "ciris_engine").is_dir():
        return home

    try:
        import ciris_engine

        package_file = getattr(ciris_engine, "__file__", None)
        if package_file:
            # ciris_engine/__init__.py → parent is ciris_engine/ → parent is install root
            return str(Path(package_file).resolve().parent.parent)
    except Exception as e:
        logger.warning(f"[tree_verify] package-relative root resolution failed: {e}")

    return None


# Canonical rules — mirror ``tools.dev.stage_runtime.ExemptRules``. Defined
# inline here (not imported) because ``tools/`` is a build-time package: the
# Docker runtime image, mobile bundles, and the wheel install all ship the
# canonical staged tree (ciris_engine + ciris_adapters + ciris_sdk) WITHOUT
# the ``tools/`` directory. Importing from ``tools.dev.stage_runtime`` at
# runtime would fail with ImportError in production. Drift protection lives
# in tests/dev/test_canonical_rules_parity.py.
_CANONICAL_INCLUDE_ROOTS: Tuple[str, ...] = ("ciris_engine", "ciris_adapters", "ciris_sdk")
_CANONICAL_EXEMPT_DIRS: Tuple[str, ...] = (
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
    "tests",
    "examples",
    "gui_static",
    "desktop_app",
)
_CANONICAL_EXEMPT_EXTENSIONS: Tuple[str, ...] = (
    "pyc",
    "pyo",
    "env",
    "log",
    "audit",
    "db",
    "sqlite",
    "sqlite3",
    "md",
    "pyi",
    "deleted",
)


def _canonical_tree_walk_rules() -> Tuple[List[str], List[str], List[str]]:
    """Return (include_roots, exempt_dirs, exempt_extensions) for the runtime walk.

    Mirrors ``tools.dev.stage_runtime.ExemptRules`` byte-for-byte — same set
    that produced /tmp/ciris-staged at CI sign time. Walking ``agent_root`` at
    runtime with these rules reproduces the same file set and therefore the
    same canonical total hash that the registered manifest carries.
    """
    return (
        list(_CANONICAL_INCLUDE_ROOTS),
        list(_CANONICAL_EXEMPT_DIRS),
        list(_CANONICAL_EXEMPT_EXTENSIONS),
    )


def run_tree_verify(
    agent_version: Optional[str] = None,
    agent_root: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Run ``verify_tree()`` and return a ``python_integrity``-shaped dict.

    Args:
        agent_version: Registry lookup version (channel suffix stripped). Defaults
            to ``get_default_agent_version()``.
        agent_root: Directory containing the include_roots. Defaults to
            ``resolve_install_root()``.

    Returns:
        Dict suitable for overlaying onto ``attestation_data["python_integrity"]``,
        or ``None`` if verify_tree was unavailable / unrunnable. Caller decides
        whether to fail-closed or fall through to other paths on ``None``.
    """
    try:
        from ciris_verify import TreeVerifyRequest, verify_tree
    except ImportError as e:
        logger.warning(f"[tree_verify] ciris_verify v1.13+ verify_tree() not available: {e}")
        return None

    if agent_version is None:
        agent_version = get_default_agent_version()
    if agent_root is None:
        agent_root = resolve_install_root()

    if not agent_version or not agent_root:
        logger.warning(
            f"[tree_verify] missing inputs: agent_version={agent_version!r} agent_root={agent_root!r}"
        )
        return None

    include_roots, exempt_dirs, exempt_extensions = _canonical_tree_walk_rules()

    logger.info(
        f"[tree_verify] verify_tree(root={agent_root}, version={agent_version}, "
        f"include={include_roots}, exempt_dirs={len(exempt_dirs)}, exempt_exts={len(exempt_extensions)})"
    )

    try:
        request = TreeVerifyRequest(
            root=agent_root,
            include_roots=include_roots,
            exempt_dirs=exempt_dirs,
            exempt_extensions=exempt_extensions,
            project="ciris-agent",
            binary_version=agent_version,
        )
        result = verify_tree(request)
    except Exception as e:
        logger.warning(f"[tree_verify] verify_tree() raised: {e}")
        return None

    # AttestationResult.python_failed_modules is typed Dict[str, str] (path → reason).
    # CIRISVerify v1.13.2's TreeVerifyResult.failed_files is List[FailedFile{path, kind}],
    # so collapse to a dict mapping each failed path to its kind label. Empty dict ≠ list:
    # passing a list here breaks pydantic validation in build_attestation_result and the
    # cache never populates, which makes every downstream thought error out at
    # `await_attestation_ready()` (see CIRISAgent#741 root cause).
    failed_modules: Dict[str, str] = {}
    for f in result.failed_files or []:
        path = getattr(f, "path", None) or str(f)
        kind = getattr(f, "kind", None)
        kind_str = kind.value if hasattr(kind, "value") else (str(kind) if kind is not None else "failed")
        failed_modules[path] = kind_str
    python_integrity: Dict[str, Any] = {
        "valid": bool(result.valid),
        "modules_checked": int(result.files_checked),
        "modules_passed": int(result.files_passed),
        "failed_modules": failed_modules,
        "total_hash": result.total_hash,
        "expected_total_hash": result.expected_total_hash,
        "registry_match": bool(result.registry_match),
        "registry_error": result.registry_error,
        "algorithm": "A",  # verify_tree → reaches L4
        "binary_version": result.binary_version,
        "project": result.project,
    }
    logger.info(
        f"[tree_verify] valid={python_integrity['valid']} "
        f"checked={python_integrity['modules_checked']} "
        f"passed={python_integrity['modules_passed']} "
        f"registry_match={python_integrity['registry_match']}"
    )
    return python_integrity
