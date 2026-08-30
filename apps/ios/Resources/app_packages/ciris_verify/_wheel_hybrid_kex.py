"""Hybrid X25519 + ML-KEM-768 KEX — Python wheel surface
(CIRISVerify#50, v4.7.0+).

Exposes the v4.6.0 `ciris_crypto::hybrid_kex` primitives to wheel
consumers so federation peers can drive harvest-now-decrypt-later-
resistant handshakes from Python.

See `src/ciris-verify-ffi/src/wheel_hybrid_kex.rs` for the underlying
FFI surface this module wraps, and `src/ciris-crypto/src/hybrid_kex.rs`
for the protocol/algorithm definitions.

## Wire shape — `algorithm: hybrid-x25519-mlkem768-hkdf-sha256-v1`

The Rust crate emits `HybridHandshakeMsg`/`ClassicalHandshakeMsg` as
serde-tagged JSON. Python callers receive a `dict` with the same
field names; bytes fields are converted to Python `bytes` at the
boundary so callers don't have to think in `list[int]`.

## Integration — `attach_to(CIRISVerify)`

This module is loaded out-of-band so the FFI surface lives in its own
file (per Eric's note: "if it ain't on the wheel, it doesn't exist").
`attach_to(cls)` mutates `cls` in place by:

1. Installing four methods (`initiate_hybrid_kex`, `respond_hybrid_kex`,
   `initiate_classical_kex`, `respond_classical_kex`).
2. Patching `cls.__init__` so the per-instance ctypes argtypes/restype
   wiring happens at instance-construction time (the wiring depends on
   `self._lib`, which only exists after `_load_library` runs from
   `__init__`).

The `_has_hybrid_kex_support` flag is set per-instance: `True` if all
four FFI symbols resolve, `False` on older wheels missing the
v4.7.0+ surface. Methods gracefully return `None` (matching the v4.2.0
conformance surface in `client.py`) when support is absent.
"""

from __future__ import annotations

import ctypes
import json
from typing import Optional


# Sentinel so attach_to is idempotent — applying it twice would
# infinitely recurse the __init__ patch.
_ATTACHED_MARKER = "_ciris_wheel_hybrid_kex_attached"


def _wire_hybrid_kex_ffi(self) -> None:
    """Wire ctypes argtypes/restype for the four v4.7.0 KEX FFI symbols.

    Sets `self._has_hybrid_kex_support` to `True` if all four symbols
    resolve, `False` otherwise. Older wheels (pre-v4.7.0) won't have
    these symbols and the call gracefully degrades.
    """
    try:
        self._lib.ciris_verify_kex_initiate_hybrid.argtypes = [
            ctypes.c_char_p,                                  # recipient_x25519_pub (32 B)
            ctypes.c_char_p,                                  # recipient_mlkem768_pub
            ctypes.c_size_t,                                  # recipient_mlkem768_pub_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_kex_initiate_hybrid.restype = ctypes.c_int

        self._lib.ciris_verify_kex_respond_hybrid_with_public.argtypes = [
            ctypes.c_char_p,                                  # recipient_x25519_priv (32 B)
            ctypes.c_char_p,                                  # recipient_mlkem768_priv
            ctypes.c_size_t,                                  # recipient_mlkem768_priv_len
            ctypes.c_char_p,                                  # recipient_mlkem768_pub
            ctypes.c_size_t,                                  # recipient_mlkem768_pub_len
            ctypes.c_char_p,                                  # msg_json
            ctypes.c_size_t,                                  # msg_json_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_kex_respond_hybrid_with_public.restype = ctypes.c_int

        self._lib.ciris_verify_kex_initiate_classical.argtypes = [
            ctypes.c_char_p,                                  # recipient_x25519_pub (32 B)
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_kex_initiate_classical.restype = ctypes.c_int

        self._lib.ciris_verify_kex_respond_classical.argtypes = [
            ctypes.c_char_p,                                  # recipient_x25519_priv (32 B)
            ctypes.c_char_p,                                  # msg_json
            ctypes.c_size_t,                                  # msg_json_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_kex_respond_classical.restype = ctypes.c_int

        self._has_hybrid_kex_support = True
    except AttributeError:
        self._has_hybrid_kex_support = False


def _take_json(self, result_ptr, result_len) -> dict:
    """Decode the malloc'd FFI buffer into a Python dict, free the buffer."""
    data = ctypes.string_at(result_ptr, result_len.value)
    self._lib.ciris_verify_free(result_ptr)
    return json.loads(data)


def _bytes_field(d: dict, key: str) -> bytes:
    """Convert a JSON `list[int]` byte field into Python `bytes`."""
    return bytes(d[key])


def _check_x25519_key(name: str, key: bytes) -> None:
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise ValueError(f"{name} must be 32 bytes (got {len(key) if isinstance(key, (bytes, bytearray)) else type(key).__name__})")


# =============================================================================
# Methods grafted onto CIRISVerify
# =============================================================================


def initiate_hybrid_kex(
    self,
    recipient_x_pub: bytes,
    recipient_mlkem_pub: bytes,
) -> Optional[dict]:
    """Initiate side: hybrid X25519 + ML-KEM-768 KEX (CIRISVerify#47/#50).

    Generates an ephemeral X25519 keypair, ECDHs against
    `recipient_x_pub`, encapsulates a fresh ML-KEM-768 shared secret
    against `recipient_mlkem_pub`, then HKDF-binds everything into a
    32-byte `session_key`. The session key is harvest-now-decrypt-later
    resistant — an attacker must break BOTH X25519 AND ML-KEM-768 to
    recover it.

    Args:
        recipient_x_pub: Recipient's long-term X25519 public key (32 B).
        recipient_mlkem_pub: Recipient's long-term ML-KEM-768 public
            key (1184 B for FIPS 203 final).

    Returns:
        `{"algorithm", "x25519_ephemeral_pub", "mlkem768_ciphertext",
        "session_key"}` — algorithm is a `str`; the other three are
        `bytes`. Send the first three fields to the peer, keep
        `session_key` local. None on older wheels missing the v4.7.0
        FFI surface.

    Raises:
        ValueError: If `recipient_x_pub` is not 32 bytes.
    """
    if not getattr(self, "_has_hybrid_kex_support", False):
        return None
    _check_x25519_key("recipient_x_pub", recipient_x_pub)

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_kex_initiate_hybrid(
        bytes(recipient_x_pub),
        bytes(recipient_mlkem_pub),
        len(recipient_mlkem_pub),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        return None
    try:
        d = _take_json(self, result_ptr, result_len)
    except Exception:
        return None
    return {
        "algorithm": d["algorithm"],
        "x25519_ephemeral_pub": _bytes_field(d, "x25519_ephemeral_pub"),
        "mlkem768_ciphertext": _bytes_field(d, "mlkem768_ciphertext"),
        "session_key": _bytes_field(d, "session_key"),
    }


def respond_hybrid_kex(
    self,
    recipient_x_priv: bytes,
    recipient_mlkem_priv: bytes,
    recipient_mlkem_pub: bytes,
    msg: dict,
) -> Optional[bytes]:
    """Respond side: derive the matching 32-byte session key.

    The session key matches what the initiator derived iff the message
    was untampered AND the recipient keys are correct. Per the v4.6.0
    opaque-failure discipline, wrong-key / tampered-ciphertext cases
    produce a *different* (but still successfully returned) session
    key — the AEAD layer above this KEX detects the mismatch as a tag
    failure. Only algorithm-identifier mismatches surface as a typed
    error.

    Args:
        recipient_x_priv: Recipient's long-term X25519 private key (32 B).
        recipient_mlkem_priv: Recipient's long-term ML-KEM-768 private key.
        recipient_mlkem_pub: Recipient's long-term ML-KEM-768 public key
            (needed for HKDF salt binding).
        msg: HybridHandshakeMsg dict from the initiator —
            `{"algorithm", "x25519_ephemeral_pub", "mlkem768_ciphertext"}`.
            Byte fields may be `bytes` or `list[int]`; both are accepted
            by the Rust serde layer.

    Returns:
        32-byte session key.

    Raises:
        ValueError: If `recipient_x_priv` is not 32 bytes.
        Exception: Wrapping the typed error envelope on
            `ALGORITHM_MISMATCH` or `MLKEM_ONLY_REJECTED`.
        None on older wheels missing the v4.7.0 FFI surface.
    """
    if not getattr(self, "_has_hybrid_kex_support", False):
        return None
    _check_x25519_key("recipient_x_priv", recipient_x_priv)

    # Normalize: msg byte-array fields must be JSON-array-of-u8 so the
    # Rust serde matches the wire shape (`HybridHandshakeMsg` declares
    # them as `[u8; 32]` and `Vec<u8>`).
    normalized = {
        "algorithm": msg["algorithm"],
        "x25519_ephemeral_pub": list(msg["x25519_ephemeral_pub"]),
        "mlkem768_ciphertext": list(msg["mlkem768_ciphertext"]),
    }
    msg_bytes = json.dumps(normalized).encode("utf-8")

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_kex_respond_hybrid_with_public(
        bytes(recipient_x_priv),
        bytes(recipient_mlkem_priv),
        len(recipient_mlkem_priv),
        bytes(recipient_mlkem_pub),
        len(recipient_mlkem_pub),
        msg_bytes,
        len(msg_bytes),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        return None
    try:
        d = _take_json(self, result_ptr, result_len)
    except Exception:
        return None
    if "error" in d:
        err = d["error"]
        # Lazy import so `_wheel_hybrid_kex.py` has no top-level
        # dependency on `exceptions.py` (keeps the file standalone
        # and importable in isolation for tests).
        from .exceptions import CIRISVerifyError
        raise CIRISVerifyError(f"{err.get('code', 'UNKNOWN')}: {err.get('message', '')}")
    return _bytes_field(d, "session_key")


def initiate_classical_kex(
    self,
    recipient_x_pub: bytes,
) -> Optional[dict]:
    """Initiate side: classical X25519-only KEX fallback.

    Used when a peer doesn't advertise ML-KEM-768 support. Identical
    shape to `initiate_hybrid_kex` minus the ML-KEM-768 ciphertext.

    Args:
        recipient_x_pub: Recipient's long-term X25519 public key (32 B).

    Returns:
        `{"algorithm", "x25519_ephemeral_pub", "session_key"}`.
        None on older wheels missing the v4.7.0 FFI surface.

    Raises:
        ValueError: If `recipient_x_pub` is not 32 bytes.
    """
    if not getattr(self, "_has_hybrid_kex_support", False):
        return None
    _check_x25519_key("recipient_x_pub", recipient_x_pub)

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_kex_initiate_classical(
        bytes(recipient_x_pub),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        return None
    try:
        d = _take_json(self, result_ptr, result_len)
    except Exception:
        return None
    return {
        "algorithm": d["algorithm"],
        "x25519_ephemeral_pub": _bytes_field(d, "x25519_ephemeral_pub"),
        "session_key": _bytes_field(d, "session_key"),
    }


def respond_classical_kex(
    self,
    recipient_x_priv: bytes,
    msg: dict,
) -> Optional[bytes]:
    """Respond side: classical X25519-only KEX fallback.

    Args:
        recipient_x_priv: Recipient's long-term X25519 private key (32 B).
        msg: ClassicalHandshakeMsg dict from the initiator —
            `{"algorithm", "x25519_ephemeral_pub"}`.

    Returns:
        32-byte session key.

    Raises:
        ValueError: If `recipient_x_priv` is not 32 bytes.
        Exception: Wrapping the typed error envelope on
            `ALGORITHM_MISMATCH`.
        None on older wheels missing the v4.7.0 FFI surface.
    """
    if not getattr(self, "_has_hybrid_kex_support", False):
        return None
    _check_x25519_key("recipient_x_priv", recipient_x_priv)

    normalized = {
        "algorithm": msg["algorithm"],
        "x25519_ephemeral_pub": list(msg["x25519_ephemeral_pub"]),
    }
    msg_bytes = json.dumps(normalized).encode("utf-8")

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_kex_respond_classical(
        bytes(recipient_x_priv),
        msg_bytes,
        len(msg_bytes),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        return None
    try:
        d = _take_json(self, result_ptr, result_len)
    except Exception:
        return None
    if "error" in d:
        err = d["error"]
        from .exceptions import CIRISVerifyError
        raise CIRISVerifyError(f"{err.get('code', 'UNKNOWN')}: {err.get('message', '')}")
    return _bytes_field(d, "session_key")


# =============================================================================
# attach_to(cls) — mutates the CIRISVerify class in place
# =============================================================================


def attach_to(cls) -> None:
    """Graft the hybrid KEX surface onto a `CIRISVerify` subclass.

    Adds the four KEX methods AND patches `cls.__init__` so the
    per-instance ctypes wiring runs after `_load_library` populates
    `self._lib`. Idempotent — calling twice is a no-op.

    Caller is responsible for invoking this exactly once during module
    import (e.g. from `client.py`):

        from ._wheel_hybrid_kex import attach_to as _attach_kex
        _attach_kex(CIRISVerify)
    """
    if getattr(cls, _ATTACHED_MARKER, False):
        return

    # Install methods first so the patched __init__ can call into
    # `_wire_hybrid_kex_ffi` without a re-entrancy footgun.
    cls._wire_hybrid_kex_ffi = _wire_hybrid_kex_ffi
    cls.initiate_hybrid_kex = initiate_hybrid_kex
    cls.respond_hybrid_kex = respond_hybrid_kex
    cls.initiate_classical_kex = initiate_classical_kex
    cls.respond_classical_kex = respond_classical_kex

    # Patch __init__ so the FFI wiring runs at the end of construction
    # — `_load_library` (called from the original __init__) is what
    # populates `self._lib`, and the argtypes wiring needs that to
    # exist. We retain a handle to the original __init__ on the class
    # so the patched __init__ doesn't capture a stale closure.
    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        # If the parent __init__ aborted before `_load_library` ran,
        # `self._lib` won't exist — flag absent support and move on.
        if getattr(self, "_lib", None) is None:
            self._has_hybrid_kex_support = False
            return
        self._wire_hybrid_kex_ffi()

    patched_init.__wrapped__ = original_init  # for introspection
    cls.__init__ = patched_init

    setattr(cls, _ATTACHED_MARKER, True)
