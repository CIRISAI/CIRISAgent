"""Runtime tree verification via the ciris-server wheel's ``ciris_verify_tree`` C symbol (Algorithm A).

This is the desktop / server / docker path to L4 file integrity. It walks
``agent_root`` on disk and compares byte-for-byte against the registered
``file_manifest_json`` for ``(project="ciris-agent", binary_version=CIRIS_VERSION)``,
using the SAME canonical algorithm that ``ciris-build-sign sign --tree`` writes
into the registry. CIRISVerify#9 / CIRISAgent#740.

The verifier is called through a thin ctypes wrapper over the C-ABI exported by
the ciris-server wheel's bundled verify library (``ciris_server.verify_ffi_path()``,
verify v10.2.0+). This replaced the standalone ``ciris-verify`` Python wheel's
``verify_tree()`` in the 2.9.7 DRY purge — the substrate owns the verifier; the
agent only surfaces its result. C contract (unchanged since CIRISVerify v1.13.0):

    ciris_verify_tree(request_json: *const c_char,
                      registry_url:  *const c_char,
                      result_out:    *mut *mut c_char) -> i32
    ciris_verify_free_string(ptr: *mut c_char)

Request/result are the JSON serializations of ``TreeVerifyRequest`` /
``TreeVerifyResult`` (see CIRISVerify ``tree_verify.rs``).

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

import ctypes
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default registry URL — matches the production deployment used by all
# downstream consumers (same constant the standalone wheel shipped).
DEFAULT_REGISTRY_URL = "https://api.registry.ciris-services-1.ai"

# Cached CDLL handle. Loaded lazily on first call; the wheel path is stable
# per-process so one load suffices.
_VERIFY_FFI_LIB: Optional[ctypes.CDLL] = None


def _load_verify_ffi_lib() -> Optional[ctypes.CDLL]:
    """Lazy-load the ciris-server wheel's verify FFI and bind ``ciris_verify_tree``.

    Returns None (with a logged warning) when the wheel or the symbol is
    unavailable — callers degrade to L3 exactly as they did when the old
    standalone ``ciris_verify`` import was missing.
    """
    global _VERIFY_FFI_LIB
    if _VERIFY_FFI_LIB is not None:
        return _VERIFY_FFI_LIB

    try:
        import ciris_server

        lib = ctypes.CDLL(str(ciris_server.verify_ffi_path()))
    except Exception as e:
        logger.warning(f"[tree_verify] ciris-server verify FFI unavailable: {e}")
        return None

    if not hasattr(lib, "ciris_verify_tree") or not hasattr(lib, "ciris_verify_free_string"):
        logger.warning(
            "[tree_verify] loaded verify FFI lacks ciris_verify_tree/ciris_verify_free_string "
            "(requires verify >= 1.13.0 in the ciris-server wheel)"
        )
        return None

    # ciris_verify_tree(request_json, registry_url, result_out) -> i32
    lib.ciris_verify_tree.argtypes = [
        ctypes.c_char_p,  # request_json (NUL-terminated)
        ctypes.c_char_p,  # registry_url (NUL-terminated)
        ctypes.POINTER(ctypes.c_char_p),  # result_out
    ]
    lib.ciris_verify_tree.restype = ctypes.c_int

    # ciris_verify_free_string(ptr) — caller frees result_out
    lib.ciris_verify_free_string.argtypes = [ctypes.c_char_p]
    lib.ciris_verify_free_string.restype = None

    _VERIFY_FFI_LIB = lib
    return lib


def _ffi_verify_tree(request: Dict[str, Any], registry_url: str = DEFAULT_REGISTRY_URL) -> Optional[Dict[str, Any]]:
    """Call ``ciris_verify_tree`` over ctypes; return the parsed TreeVerifyResult dict.

    Returns None (with a logged warning) on any FFI-level failure — load
    failure, non-zero return code, empty/unparseable result.
    """
    lib = _load_verify_ffi_lib()
    if lib is None:
        return None

    result_ptr = ctypes.c_char_p()
    rc = lib.ciris_verify_tree(
        json.dumps(request).encode("utf-8"),
        registry_url.encode("utf-8"),
        ctypes.byref(result_ptr),
    )
    if rc != 0:
        logger.warning(f"[tree_verify] ciris_verify_tree failed with code {rc}")
        return None

    try:
        raw = result_ptr.value
        if not raw:
            logger.warning("[tree_verify] ciris_verify_tree returned empty result")
            return None
        result_json = raw.decode("utf-8")
    finally:
        if result_ptr.value:
            lib.ciris_verify_free_string(result_ptr)

    try:
        parsed = json.loads(result_json)
    except (ValueError, TypeError) as e:
        logger.warning(f"[tree_verify] ciris_verify_tree result unparseable: {e}")
        return None
    if not isinstance(parsed, dict):
        logger.warning(f"[tree_verify] ciris_verify_tree result not an object: {type(parsed).__name__}")
        return None
    return parsed


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
    project: str = "ciris-agent",
) -> Optional[Dict[str, Any]]:
    """Run the substrate tree verifier and return a ``python_integrity``-shaped dict.

    Args:
        agent_version: Registry lookup version (channel suffix stripped). Defaults
            to ``get_default_agent_version()``.
        agent_root: Directory containing the include_roots. Defaults to
            ``resolve_install_root()``.
        project: Registry project to verify the tree against. Defaults to
            ``"ciris-agent"`` (the agent's own source tree). ``ciris_verify_tree``
            is project-agnostic, so a sibling substrate can pass
            its own project (e.g. ``"ciris-lens-core"`` / ``"ciris-edge"``) to
            verify a different registered manifest (CIRISAgent#754).

    Returns:
        Dict suitable for overlaying onto ``attestation_data["python_integrity"]``,
        or ``None`` if the verifier was unavailable / unrunnable. Caller decides
        whether to fail-closed or fall through to other paths on ``None``.
    """
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
        f"[tree_verify] ciris_verify_tree(project={project}, root={agent_root}, version={agent_version}, "
        f"include={include_roots}, exempt_dirs={len(exempt_dirs)}, exempt_exts={len(exempt_extensions)})"
    )

    try:
        result = _ffi_verify_tree(
            {
                "root": agent_root,
                "include_roots": include_roots,
                "exempt_dirs": exempt_dirs,
                "exempt_extensions": exempt_extensions,
                "project": project,
                "binary_version": agent_version,
            }
        )
    except Exception as e:
        logger.warning(f"[tree_verify] ciris_verify_tree raised: {e}")
        return None
    if result is None:
        return None

    # AttestationResult.python_failed_modules is typed Dict[str, str] (path → reason).
    # TreeVerifyResult.failed_files is a list of FailedFile{path, kind} objects,
    # so collapse to a dict mapping each failed path to its kind label. Empty dict ≠ list:
    # passing a list here breaks pydantic validation in build_attestation_result and the
    # cache never populates, which makes every downstream thought error out at
    # `await_attestation_ready()` (see CIRISAgent#741 root cause).
    #
    # v1.14.0 split: `failed_files` contains ONLY hard failures (hash_mismatch,
    # extra). Files in the manifest but not on disk live in `missing_files`, which
    # we track separately as `missing_modules` — soft/informational rather than
    # an L4-gating failure. CIRISVerify#15 → CIRISAgent#742. Build-time-only
    # artifacts like `_build_secrets.py` (mobile bundles ship it for the wallet
    # provider's runtime secrets read; desktop wheel intentionally excludes it
    # for distribution security) appear here on desktop installs and shouldn't
    # block L4.
    def _file_entries(entries: Any, default_kind: str) -> Dict[str, str]:
        collapsed: Dict[str, str] = {}
        for f in entries or []:
            if not isinstance(f, dict):
                collapsed[str(f)] = default_kind
                continue
            path = str(f.get("path") or f)
            kind = f.get("kind")
            collapsed[path] = str(kind) if kind is not None else default_kind
        return collapsed

    failed_modules = _file_entries(result.get("failed_files"), "failed")
    missing_modules = _file_entries(result.get("missing_files"), "missing")

    # Field names mirror what result_builder._build_python_integrity_fields()
    # reads (those keys date back to Algorithm B). Specifically:
    #   - "actual_total_hash" (NOT "total_hash") — the field result_builder
    #     copies into AttestationResult.python_total_hash. Using "total_hash"
    #     leaves the API response field empty even though the verifier
    #     produced a real hash. Caught by L4_ATTESTATION QA module.
    #   - "modules_failed" (count, NOT "failed_modules" the dict) — the field
    #     result_builder copies into python_modules_failed.
    #   - "total_hash_valid" — boolean, distinct from registry_match.
    expected_total_hash = result.get("expected_total_hash")
    total_hash = result.get("total_hash")
    python_integrity: Dict[str, Any] = {
        "valid": bool(result.get("valid")),
        "modules_checked": int(result.get("files_checked") or 0),
        "modules_passed": int(result.get("files_passed") or 0),
        "modules_failed": len(failed_modules),  # only hard failures, not missing
        "failed_modules": failed_modules,
        "modules_missing": len(missing_modules),
        "missing_modules": missing_modules,
        "actual_total_hash": total_hash,
        "total_hash_valid": bool(expected_total_hash) and total_hash == expected_total_hash,
        "expected_total_hash": expected_total_hash,
        "registry_match": bool(result.get("registry_match")),
        "registry_error": result.get("registry_error"),
        "algorithm": "A",  # tree verifier → reaches L4
        "binary_version": result.get("binary_version"),
        "project": result.get("project"),
    }
    logger.info(
        f"[tree_verify] valid={python_integrity['valid']} "
        f"checked={python_integrity['modules_checked']} "
        f"passed={python_integrity['modules_passed']} "
        f"failed={python_integrity['modules_failed']} "
        f"missing={python_integrity['modules_missing']} "
        f"registry_match={python_integrity['registry_match']}"
    )
    return python_integrity
