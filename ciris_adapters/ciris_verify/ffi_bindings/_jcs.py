"""JCS (RFC 8785) canonicalization — Python binding (CIRISVerify#61).

Exposes :func:`jcs_canonicalize`, a thin wrapper over the FFI symbol
``ciris_verify_jcs_canonicalize`` which calls
``ciris_verify_core::jcs::canonicalize`` (the one blessed JCS impl, shipped
v4.11.0). The CIRISAgent producer uses this so its signing canonical bytes
are **byte-identical** to what the Rust verifiers recompute at the CEG §0.9
JCS cutover (the 2.9.6 substrate triple).

Why this is correct by construction: this module does **no** canonicalization
itself. It serializes the value to *any* valid JSON encoding (``json.dumps``)
purely as a transport into Rust, where JCS canonicalization happens. JCS
canonicalizes by *value*, so the transport encoding is irrelevant and the
output is identical to the Rust path — there is no second implementation to
keep in lockstep, which is exactly the divergence the cutover eliminates
(Python's ``json.dumps`` is itself NOT JCS and breaks on all non-ASCII).
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Any, Optional

__all__ = ["jcs_canonicalize"]

# Process-wide lazy handle to the shared library. The JCS function is
# stateless (no engine / runtime), so we load the cdylib directly rather
# than constructing a full CIRISVerify (which spins up the tokio runtime
# + license engine).
_lib: Optional[ctypes.CDLL] = None
_lib_lock = _threading.Lock()
_SUCCESS = 0


def _candidate_paths() -> list[str]:
    """Library search paths, substrate-first (CIRISAgent#917).

    Order: the ciris-server wheel's folded verify FFI, then the standalone
    ``ciris-verify`` wheel layout (legacy), then the package's documented
    install + dev paths."""
    here = Path(__file__).resolve().parent
    system = _platform.system()
    names = {
        "Linux": ["libciris_verify_ffi.so", "libciris_verify.so"],
        "Darwin": ["libciris_verify_ffi.dylib", "libciris_verify.dylib"],
        "Windows": ["ciris_verify_ffi.dll", "ciris_verify.dll"],
    }.get(system, ["libciris_verify_ffi.so"])

    paths: list[str] = []
    # 1. THE SUBSTRATE'S OWN verify (CIRISAgent#917). ciris-server folds
    #    ciris-verify-ffi directly into ciris_server._native (CIRISServer#232),
    #    exporting all 88 ciris_verify_* C symbols — ciris_verify_jcs_canonicalize
    #    among them. Binding here means the producer's canonical bytes come from
    #    the SAME verify the substrate's Rust verifiers recompute with, so JCS
    #    skew is impossible by construction rather than by pin discipline. This
    #    is the identical loader hop attestation/tree_verify.py takes for
    #    ciris_verify_tree; keep the two in step.
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

        paths.append(str(ciris_server.verify_ffi_path()))
    except Exception:  # pragma: no cover - defensive
        pass
    # 2. Alongside this module (the standalone-wheel layout). LEGACY fallback:
    #    the ciris-verify pin was dropped once #917 landed, so this only fires
    #    in environments that still carry the standalone package.
    for n in names:
        paths.append(str(here / n))
    # 3. The package's documented default install + dev paths.
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
                fn = lib.ciris_verify_jcs_canonicalize
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            fn.argtypes = [
                ctypes.c_char_p,  # input_json (UTF-8 bytes)
                ctypes.c_size_t,  # input_len
                ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),  # result_out
                ctypes.POINTER(ctypes.c_size_t),  # result_len_out
            ]
            fn.restype = ctypes.c_int
            lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
            lib.ciris_verify_free.restype = None
            _lib = lib
            return _lib
    raise RuntimeError(
        "ciris_verify_jcs_canonicalize not available — could not load "
        f"the CIRISVerify shared library (last error: {last_err}). "
        "The library must be built with the wheel (>= v5.0.0)."
    )


def jcs_canonicalize(value: Any) -> bytes:
    """Canonicalize a JSON value to its RFC 8785 (JCS) byte sequence.

    Args:
        value: a JSON-able value (``dict`` / ``list`` / ``str`` / ``int`` /
            ``float`` / ``bool`` / ``None``), **or** a ``str``/``bytes``
            already containing a JSON document (passed through to the
            canonicalizer as-is).

    Returns:
        The exact RFC 8785 canonical byte sequence — byte-identical to
        ``ciris_verify_core::jcs::canonicalize`` and therefore to what the
        Rust verifiers recompute.

    Raises:
        ValueError: the value is not valid JSON / cannot be canonicalized.
        RuntimeError: the shared library / FFI symbol is unavailable.
    """
    if isinstance(value, bytes):
        input_bytes = value
    elif isinstance(value, str):
        # Already a JSON document string — transport as-is.
        input_bytes = value.encode("utf-8")
    else:
        # ensure_ascii=False keeps non-ASCII as literal UTF-8; the Rust
        # parser handles both forms identically (JCS canonicalizes by
        # value), so this is purely a transport choice.
        input_bytes = _json.dumps(value, ensure_ascii=False).encode("utf-8")

    lib = _load_lib()
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = lib.ciris_verify_jcs_canonicalize(
        input_bytes,
        len(input_bytes),
        ctypes.byref(out_ptr),
        ctypes.byref(out_len),
    )
    if rc != _SUCCESS:
        # rc 2 == SerializationError in the CirisVerifyError enum.
        raise ValueError(f"jcs_canonicalize: input is not valid JSON or cannot be " f"canonicalized (FFI code {rc})")
    n = out_len.value
    if n == 0:
        return b""
    try:
        result = ctypes.string_at(out_ptr, n)
    finally:
        lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return result
