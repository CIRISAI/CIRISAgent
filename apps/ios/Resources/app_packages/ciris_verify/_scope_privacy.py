"""Scope-native privacy derivations — Python binding (CIRISVerify#82).

Exposes the ``ciris_crypto::scope_privacy`` FSD §2.2/§2.4/§3.4 derivation
helpers (CEWP ``SCOPE_PRIVACY.md`` — CC 1.13.3 anonymous tier) on the wheel,
over the FFI symbol ``ciris_verify_scope_privacy_derive``. A Python consumer can
reproduce a ``record_id`` / ``symbol_key`` / witness cover-leaf **byte-identically**
to the Rust verifiers — the canonical bytes (incl. the RFC 8949 §4.2.1
deterministic CBOR ``record_id`` preimage and the pinned ``RecordType`` integers)
come from the one Rust impl, so there is no second implementation to drift.

Imported as the ``ciris_verify.scope_privacy`` namespace::

    from ciris_verify import scope_privacy
    krid = scope_privacy.k_record_id(exporter_secret)
    rid  = scope_privacy.derive_record_id(krid, internal_id, "community", epoch)
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Optional

__all__ = [
    "k_record_id",
    "k_symbol",
    "derive_record_id",
    "derive_symbol_key",
    "witness_cover_leaf",
]

_lib: Optional[ctypes.CDLL] = None
_lib_lock = _threading.Lock()
_SUCCESS = 0

# The record_type strings the FFI accepts (mirrors ciris_crypto RecordType).
_RECORD_TYPES = ("self", "family", "community", "federation")


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
                fn = lib.ciris_verify_scope_privacy_derive
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
        "ciris_verify_scope_privacy_derive not available — could not load "
        f"the CIRISVerify shared library (last error: {last_err}). "
        "The library must be built with the wheel (>= v7.4.0)."
    )


def _derive(req: dict) -> bytes:
    input_bytes = _json.dumps(req).encode("utf-8")
    lib = _load_lib()
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = lib.ciris_verify_scope_privacy_derive(
        input_bytes,
        len(input_bytes),
        ctypes.byref(out_ptr),
        ctypes.byref(out_len),
    )
    if rc != _SUCCESS:
        # rc 2 == SerializationError (bad request / wrong-length key / unknown type).
        raise ValueError(
            f"scope_privacy: invalid request — a 32-byte key has the wrong length, "
            f"an unknown record_type, or non-encodable input (FFI code {rc})"
        )
    n = out_len.value
    try:
        result = ctypes.string_at(out_ptr, n)
    finally:
        if n != 0:
            lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return result


def k_record_id(exporter_secret: bytes) -> bytes:
    """§2.2 — derive ``K_record_id`` from the group's 32-byte MLS exporter secret."""
    return _derive({"op": "k_record_id", "exporter_secret": list(exporter_secret)})


def k_symbol(exporter_secret: bytes) -> bytes:
    """§2.2 — derive ``K_symbol`` from the group's 32-byte MLS exporter secret."""
    return _derive({"op": "k_symbol", "exporter_secret": list(exporter_secret)})


def derive_record_id(
    k_record_id: bytes,
    internal_id: bytes,
    record_type: str,
    mls_group_epoch: int,
) -> bytes:
    """§2.4 — ``record_id = HMAC-SHA3-256(K_record_id, CBOR_dCE({v,iid,typ,epc}))``.

    ``record_type`` is one of ``"self"``, ``"family"``, ``"community"``,
    ``"federation"`` (the pinned ``RecordType`` mapping). The CBOR preimage is
    RFC 8949 §4.2.1 core-deterministic — encoded Rust-side, so this is
    byte-identical to the verifier's ``record_id``.
    """
    if record_type not in _RECORD_TYPES:
        raise ValueError(f"record_type must be one of {_RECORD_TYPES}, got {record_type!r}")
    return _derive(
        {
            "op": "record_id",
            "k_record_id": list(k_record_id),
            "internal_id": list(internal_id),
            "record_type": record_type,
            "mls_group_epoch": int(mls_group_epoch),
        }
    )


def derive_symbol_key(k_symbol: bytes, record_id: bytes, symbol_index: int) -> bytes:
    """§2.4 — ``symbol_key = HKDF-SHA3-256(salt=record_id, ikm=K_symbol, info=label‖u16(idx))``."""
    return _derive(
        {
            "op": "symbol_key",
            "k_symbol": list(k_symbol),
            "record_id": list(record_id),
            "symbol_index": int(symbol_index),
        }
    )


def witness_cover_leaf(
    witness_signing_key: bytes,
    leaf_position: int,
    federation_epoch_id: int,
) -> bytes:
    """§3.4 — witness cover-leaf ``HMAC-SHA3-256(key, u32_be(pos) ‖ u64_be(epoch))``."""
    return _derive(
        {
            "op": "witness_cover_leaf",
            "witness_signing_key": list(witness_signing_key),
            "leaf_position": int(leaf_position),
            "federation_epoch_id": int(federation_epoch_id),
        }
    )
