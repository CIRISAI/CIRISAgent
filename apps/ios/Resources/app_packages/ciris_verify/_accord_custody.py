"""Accord-holder custody attestation — Python binding (CIRISVerify#91).

Exposes :func:`verify_accord_custody_attestation`, a thin wrapper over the FFI
symbol ``ciris_verify_accord_custody_attestation`` which calls
``ciris_verify_core::accord_custody_attestation`` — the hardware-unforgeable
YubiKey-PIV custody check the CIRISServer admission gate runs before admitting a
holder to the accord kill-switch roster (the CIRISServer#41 safe-mesh floor).

There is exactly one blessed implementation of the check; the wheel reaches it
rather than reimplement the PIV chain walk. The function is **fail-closed**: a
negative admission (chain invalid, floor not met, wrong attested key) is a
successful call returning ``admitted = False`` with a ``reason``, never an
exception. Only a malformed request raises :class:`ValueError`.
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Any, Optional

__all__ = ["verify_accord_custody_attestation"]

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


def _wire(fn: Any) -> None:
    fn.argtypes = [
        ctypes.c_char_p,  # input_json (UTF-8 bytes)
        ctypes.c_size_t,  # input_len
        ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),  # result_out
        ctypes.POINTER(ctypes.c_size_t),  # result_len_out
    ]
    fn.restype = ctypes.c_int


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
                _wire(lib.ciris_verify_accord_custody_attestation)
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
            lib.ciris_verify_free.restype = None
            _lib = lib
            return _lib
    raise RuntimeError(
        "accord-custody FFI symbol not available — could not load the "
        f"CIRISVerify shared library (last error: {last_err}). The library "
        "must be built with the wheel (>= v6.7.0)."
    )


def verify_accord_custody_attestation(
    attestation_object: Any,
    holder_member: dict,
    yubico_root_der_hex: str,
) -> dict:
    """Verify an accord-holder custody attestation (CIRISVerify#91).

    Args:
        attestation_object: the signed ``accord_holder_custody_attestation``
            CEG object (a JSON-able value, as produced by the holder ceremony).
        holder_member: the holder's pinned hybrid pubkeys, resolved by the
            caller from its directory by the bundle's ``holder_key_id`` —
            ``{"member_id": "...", "ed25519_public_key_base64": "...",
            "mldsa65_public_key_base64": "..."}``.
        yubico_root_der_hex: the **pinned** Yubico PIV attestation root, as
            hex-encoded DER. The consumer pins the trust root; verify provides
            only the verification.

    Returns:
        On admission: ``{"admitted": True, "hardware_class": "YubiKey_5_FIPS",
        "custody_tier": ..., "firmware": ..., "serial": int?,
        "fips_certified": True, "touch_always": True}``. On rejection:
        ``{"admitted": False, "reason": "..."}``. Admit **only** on
        ``admitted is True``.

    Raises:
        ValueError: the request itself is malformed (a caller error, NOT a
            negative verdict — e.g. a non-hex root).
        RuntimeError: the shared library / FFI symbol is unavailable.
    """
    lib = _load_lib()
    request = {
        "attestation_object": attestation_object,
        "holder_member": holder_member,
        "yubico_root_der_hex": yubico_root_der_hex,
    }
    body = _json.dumps(request, ensure_ascii=False).encode("utf-8")
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = lib.ciris_verify_accord_custody_attestation(
        body, len(body), ctypes.byref(out_ptr), ctypes.byref(out_len)
    )
    if rc != _SUCCESS:
        raise ValueError(
            f"verify_accord_custody_attestation: malformed request (FFI code "
            f"{rc}) — this is a caller error, distinct from a fail-closed "
            "negative verdict"
        )
    n = out_len.value
    if n == 0:
        return {}
    try:
        raw = ctypes.string_at(out_ptr, n)
    finally:
        lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return _json.loads(raw)
