"""RNS ``destination_hash`` recompute — Python binding (CIRISVerify#28).

Exposes :func:`rns_destination_hash`, a thin wrapper over the FFI symbol
``ciris_verify_rns_destination_hash`` which calls
``ciris_verify_core::transport_binding::compute_destination_hash`` — the one
blessed two-stage RNS destination-hash construction (CEG 1.0-RC6 §5.6.8.8.1.1).

This lifts the last verify-side remainder of the #28 transport-binding
waterfall: the recompute shipped Rust-side in v5.6.0 (``DestinationHashCheck``
lifted off ``Unsupported``) but was never on the wheel, so a Python consumer —
and CIRISConformance's ``test_150_rns_dest_hash.py`` cross-check — could not
verify a peer's ``destination_hash`` against the pinned algorithm. With this it
can, byte-for-byte, with **no** Reticulum vendoring and no second
implementation: the canonical bytes come from the same Rust path the verifiers
use.
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Optional, Sequence

__all__ = ["rns_destination_hash"]

_lib: Optional[ctypes.CDLL] = None
_lib_lock = _threading.Lock()
_SUCCESS = 0


def _candidate_paths() -> list[str]:
    here = Path(__file__).resolve().parent
    system = _platform.system()
    names = {
        "Linux": ["libciris_verify_ffi.so", "libciris_verify.so"],
        "Darwin": ["libciris_verify_ffi.dylib", "libciris_verify.dylib"],
        "Windows": ["ciris_verify_ffi.dll", "ciris_verify.dll"],
    }.get(system, ["libciris_verify_ffi.so"])

    paths: list[str] = []
    for n in names:
        paths.append(str(here / n))
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
                fn = lib.ciris_verify_rns_destination_hash
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
        "ciris_verify_rns_destination_hash not available — could not load "
        f"the CIRISVerify shared library (last error: {last_err}). "
        "The library must be built with the wheel (>= v7.3.0)."
    )


def rns_destination_hash(
    app_name: str,
    aspects: Sequence[str],
    x25519_pub: bytes,
    ed25519_pub: bytes,
) -> bytes:
    """Recompute the RNS ``destination_hash`` per CEG §5.6.8.8.1.1.

    The two-stage construction (NOT a flat single SHA-256):

        name_hash        = SHA256(app_name + "." + ".".join(aspects))[:10]
        identity_hash    = SHA256(x25519_pub ‖ ed25519_pub)[:16]
        destination_hash = SHA256(name_hash ‖ identity_hash)[:16]

    Args:
        app_name: the RNS app name (e.g. ``"ciris.federation"``).
        aspects: the dot-joined aspects (each MUST NOT contain ``"."``).
        x25519_pub: the peer's X25519 public key bytes.
        ed25519_pub: the peer's Ed25519 public key bytes (key order is
            x25519 THEN ed25519, per RNS ``get_public_key``).

    Returns:
        The 16-byte destination hash — byte-identical to
        ``ciris_verify_core::transport_binding::compute_destination_hash`` and
        therefore to the pinned §5.6.8.8.1.1 algorithm.

    Raises:
        ValueError: an aspect contains ``"."`` (illegal — it would alter the
            name preimage split), or the inputs cannot be encoded.
        RuntimeError: the shared library / FFI symbol is unavailable.
    """
    req = {
        "app_name": app_name,
        "aspects": list(aspects),
        "x25519_pubkey": list(x25519_pub),
        "ed25519_pubkey": list(ed25519_pub),
    }
    input_bytes = _json.dumps(req).encode("utf-8")

    lib = _load_lib()
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = lib.ciris_verify_rns_destination_hash(
        input_bytes,
        len(input_bytes),
        ctypes.byref(out_ptr),
        ctypes.byref(out_len),
    )
    if rc != _SUCCESS:
        # rc 2 == SerializationError (bad request / dotted aspect).
        raise ValueError(
            f"rns_destination_hash: invalid request (e.g. an aspect containing "
            f"'.', or non-encodable input) (FFI code {rc})"
        )
    n = out_len.value
    try:
        result = ctypes.string_at(out_ptr, n)
    finally:
        if n != 0:
            lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return result
