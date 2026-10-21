"""test-anchor deploy probe — Python binding (CIRISVerify#202).

Exposes :func:`test_anchor_compiled_in`, a thin wrapper over the FFI symbol
``ciris_verify_test_anchor_compiled_in`` (present in EVERY build). It returns
``True`` iff this artifact was built with the **test-only** ``test-anchor``
Cargo feature — the software trust-root / software accord-holder relaxation that
must never ship in a production wheel.

**Deploy gate:** require ``test_anchor_compiled_in() is False`` on the shipped
wheel before a production deploy. A ``True`` is a release-process failure (the
wheel was built with ``--features test-anchor``). See
``docs/RELEASE_CHECKLIST.md``.
"""

from __future__ import annotations

import ctypes
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Optional

__all__ = ["test_anchor_compiled_in"]

_lib: Optional[ctypes.CDLL] = None
_lib_lock = _threading.Lock()


def _candidate_paths() -> list[str]:
    here = Path(__file__).resolve().parent
    system = _platform.system()
    names = {
        "Linux": ["libciris_verify_ffi.so", "libciris_verify.so"],
        "Darwin": ["libciris_verify_ffi.dylib", "libciris_verify.dylib"],
        "Windows": ["ciris_verify_ffi.dll", "ciris_verify.dll"],
    }.get(system, ["libciris_verify_ffi.so"])
    paths: list[str] = [str(here / n) for n in names]
    try:
        from .client import DEFAULT_BINARY_PATHS  # type: ignore

        paths.extend(DEFAULT_BINARY_PATHS.get(system, []))
    except Exception:  # pragma: no cover - defensive
        pass
    return paths


def _load_lib() -> ctypes.CDLL:
    global _lib
    if _lib is not None:
        return _lib
    with _lib_lock:
        if _lib is not None:
            return _lib
        last_err: Optional[Exception] = None
        for path in _candidate_paths():
            if not Path(path).exists():
                continue
            try:
                lib = ctypes.CDLL(path)
                lib.ciris_verify_test_anchor_compiled_in.argtypes = []
                lib.ciris_verify_test_anchor_compiled_in.restype = ctypes.c_int
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            _lib = lib
            return _lib
    raise RuntimeError(
        "test-anchor probe symbol not available — could not load the CIRISVerify "
        f"shared library (last error: {last_err})."
    )


def test_anchor_compiled_in() -> bool:
    """Whether the TEST-ONLY ``test-anchor`` bypass is compiled into this artifact.

    ``True`` means the software trust-root / software accord-holder relaxation is
    present — which must NEVER be the case for a production wheel. Use as a deploy
    gate: ``assert not test_anchor_compiled_in()``.
    """
    return bool(_load_lib().ciris_verify_test_anchor_compiled_in())
