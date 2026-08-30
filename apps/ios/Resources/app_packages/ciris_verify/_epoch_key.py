"""CC 5.1 ``CLM-epoch-keying`` derivations — Python binding (CIRISVerify#193).

Per-``(stream_id, epoch)`` DEK + stream-nonce HKDF derivation — the epoch-keyed
counterpart of :func:`ciris_verify.scope_privacy.derive_symbol_key`. Two
different epochs (or streams) yield independent keys, so compromise of one
epoch's DEK reveals nothing about any other (**epoch isolation**).

The canonical bytes come from the one Rust impl over the FFI symbol
``ciris_verify_epoch_key_derive`` — no second implementation, so the
CIRISConformance CC 5.1 goldens hold by construction.

    from ciris_verify import derive_epoch_key, derive_epoch_stream_nonce
    dek   = derive_epoch_key(stream_root, "stream-1", 7)          # 32 bytes
    nonce = derive_epoch_stream_nonce(stream_root, "stream-1", 7) # 24 bytes

Formula (pinned; a change is a wire break)::

    info(label, stream_id, epoch) = utf8(label) || u32_be(len(stream_id))
                                              || utf8(stream_id) || u64_be(epoch)
    epoch_key   = HKDF-SHA256(salt="CIRIS-epoch-key-v1", ikm=stream_root,
                              info=info("ciris/clm/epoch-dek/v1",   ...), L=32)
    epoch_nonce = HKDF-SHA256(salt="CIRIS-epoch-key-v1", ikm=stream_root,
                              info=info("ciris/clm/epoch-nonce/v1", ...), L=24)
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Optional

__all__ = ["derive_epoch_key", "derive_epoch_stream_nonce"]

_lib: Optional[ctypes.CDLL] = None
_lib_lock = _threading.Lock()
_SUCCESS = 0

#: Stream-nonce length (XChaCha20-Poly1305).
EPOCH_NONCE_LEN = 24


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
                fn = lib.ciris_verify_epoch_key_derive
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
        "ciris_verify_epoch_key_derive not available — could not load the "
        f"CIRISVerify shared library (last error: {last_err}). "
        "The library must be built with the wheel (>= v10.1.0)."
    )


def _derive(req: dict) -> bytes:
    input_bytes = _json.dumps(req).encode("utf-8")
    lib = _load_lib()
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = lib.ciris_verify_epoch_key_derive(
        input_bytes,
        len(input_bytes),
        ctypes.byref(out_ptr),
        ctypes.byref(out_len),
    )
    if rc != _SUCCESS:
        raise ValueError(
            "epoch_key: invalid request — stream_root must be exactly 32 bytes "
            f"(FFI code {rc})"
        )
    n = out_len.value
    try:
        result = ctypes.string_at(out_ptr, n)
    finally:
        if n != 0:
            lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return result


def _check(stream_root: bytes, epoch: int) -> None:
    if len(stream_root) != 32:
        raise ValueError(f"stream_root must be 32 bytes, got {len(stream_root)}")
    if epoch < 0 or epoch > 0xFFFF_FFFF_FFFF_FFFF:
        raise ValueError("epoch must fit in a u64")


def derive_epoch_key(stream_root: bytes, stream_id: str, epoch: int) -> bytes:
    """CC 5.1 — the **per-epoch DEK** (32 bytes) for ``(stream_id, epoch)``.

    Deterministic; epochs and streams are cryptographically isolated.
    """
    _check(stream_root, epoch)
    return _derive(
        {
            "op": "epoch_key",
            "stream_root": list(stream_root),
            "stream_id": stream_id,
            "epoch": epoch,
        }
    )


def derive_epoch_stream_nonce(stream_root: bytes, stream_id: str, epoch: int) -> bytes:
    """CC 5.1 — the **per-epoch stream nonce** (24 bytes, XChaCha20-Poly1305).

    Derived under a DISTINCT domain label from :func:`derive_epoch_key`, so the
    nonce is cryptographically independent of the DEK.
    """
    _check(stream_root, epoch)
    return _derive(
        {
            "op": "epoch_stream_nonce",
            "stream_root": list(stream_root),
            "stream_id": stream_id,
            "epoch": epoch,
        }
    )
