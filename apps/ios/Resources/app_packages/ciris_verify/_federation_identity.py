"""Hardware-rooted federation identity creation — Python binding (CIRISVerify 6.0, #63).

Exposes :func:`create_federation_identity`, a thin wrapper over the FFI symbol
``ciris_verify_create_federation_identity`` (``ciris_verify_core::
federation_identity::create_federation_identity``). A server-side / desktop
Python consumer calls this to mint the owner's federation identity: the Ed25519
owner-binding half is rooted in the best available platform hardware (Secure
Enclave / StrongBox / TPM-sealed, software fallback) and auto-provisioned on
first call; the ML-DSA-65 PQC half is a software seed. The result is a
self-signed genesis ``KeyRecord`` CEG object, optionally written to
``<ciris>/ceg/outbox/`` for CIRISServer to drain + relay.

The YubiKey-PIV token path is the desktop ``ciris-verify identity create`` CLI
(``--provision``); mobile/KMP clients call this same C symbol via cinterop.
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Any, Optional

__all__ = ["create_federation_identity"]

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
                fn = lib.ciris_verify_create_federation_identity
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            fn.argtypes = [
                ctypes.c_char_p,  # config_json (UTF-8 bytes)
                ctypes.POINTER(ctypes.c_void_p),  # result_out (char**)
            ]
            fn.restype = ctypes.c_int
            lib.ciris_verify_free_string.argtypes = [ctypes.c_void_p]
            lib.ciris_verify_free_string.restype = None
            _lib = lib
            return _lib
    raise RuntimeError(
        "ciris_verify_create_federation_identity not available — could not load "
        f"the CIRISVerify shared library (last error: {last_err}). "
        "The library must be built with the wheel (>= 6.0.0)."
    )


def create_federation_identity(config: dict[str, Any]) -> dict[str, Any]:
    """Create a hardware-rooted federation identity.

    Args:
        config: a dict with keys —
            ``alias`` (str, platform key-store alias; default ``"federation-user"``),
            ``seed_dir`` (str, REQUIRED — where the sealed Ed25519 + ML-DSA seeds live),
            ``identity_type`` (``"user"`` | ``"agent"``; default ``"user"``),
            ``fed_key_id`` (str | None; default ``sha256(ed_pubkey)`` hex),
            ``label`` (str | None; for the ``label-fingerprint`` derived key_id),
            ``seal_alias`` (str | None; CIRISVerify#89 — key the ML-DSA seal under a
                stable keystore alias while recording under the derived ``key_id``,
                so a switch to derived key_ids needs no custody re-open. Omit for
                back-compat: the seal is keyed by ``key_id``),
            ``valid_from`` (RFC-3339 str; default host-now),
            ``write_outbox`` (bool; default ``True``).

    Returns:
        The decoded result dict: ``{"ok": True, "key_id": ..., "outbox_path":
        ..., "ceg_object": {...}}``.

    Raises:
        RuntimeError: the FFI call failed, or the operation returned
            ``{"ok": false, "error": ...}``.
    """
    lib = _load_lib()
    cfg_bytes = _json.dumps(config).encode("utf-8")
    out = ctypes.c_void_p()
    rc = lib.ciris_verify_create_federation_identity(cfg_bytes, ctypes.byref(out))
    if rc != _SUCCESS:
        raise RuntimeError(f"create_federation_identity: FFI error code {rc}")
    if not out.value:
        raise RuntimeError("create_federation_identity: FFI returned no result")
    try:
        raw = ctypes.cast(out, ctypes.c_char_p).value
    finally:
        lib.ciris_verify_free_string(out)
    result = _json.loads(raw.decode("utf-8")) if raw else {}
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "create_federation_identity failed"))
    return result
