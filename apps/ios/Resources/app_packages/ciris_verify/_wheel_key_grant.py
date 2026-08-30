"""Python wheel surface for the v4.4.0 ``key_grant`` HPKE-shape
wrap/unwrap primitive (CIRISVerify#44, exposed for Python wheel
consumers per CIRISVerify#50 / v4.7.0 wheel-surface work).

Eric's principle: "if it ain't on the wheel, it doesn't exist."
The Rust crate at ``ciris_crypto::key_grant`` ships
``wrap_dek_for_recipient`` / ``unwrap_dek`` for the
``x25519-aes256-gcm-hkdf-sha256`` algorithm — this module is the
``CIRISVerify`` Python class's stateless boundary into that surface.

Usage from ``client.py`` (one line at the bottom of the file, after
the ``CIRISVerify`` class body)::

    from ._wheel_key_grant import attach_to as _attach_key_grant_surface
    _attach_key_grant_surface(CIRISVerify)

After that, instances expose:

- ``wrap_dek_for_recipient(recipient_x_pub: bytes, dek: bytes) -> dict``
- ``unwrap_dek(recipient_x_priv: bytes, wrap: dict) -> bytes``

Both raise :class:`ciris_verify.exceptions.CIRISVerifyError` on FFI
failure or older-library-missing-symbol cases. The unwrap method
specifically raises ``CIRISVerifyError("WRAP_UNVERIFIED: ...")`` on
the opaque AEAD-failure case (wrong recipient key, tampered
ciphertext, swapped ephemeral_public_key, or tampered nonce — all
the same opaque-failure category per the AEAD discipline).
"""

from __future__ import annotations

import ctypes
import json
from typing import Any, Dict, Optional

from .exceptions import CIRISVerifyError


def _wire_key_grant_ffi(self: Any) -> None:
    """Wire ctypes argtypes/restype for the 2 key-grant FFI symbols.

    Sets ``self._has_key_grant_support`` to True iff both symbols
    are present in the loaded library. Older libraries (pre-v4.7.0)
    will hit ``AttributeError`` and the methods will degrade to
    raising ``CIRISVerifyError`` on call.
    """
    try:
        self._lib.ciris_verify_wrap_dek_for_recipient.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),                    # recipient_pub[32]
            ctypes.POINTER(ctypes.c_uint8),                    # dek[32]
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),    # result_out
            ctypes.POINTER(ctypes.c_size_t),                   # result_len_out
        ]
        self._lib.ciris_verify_wrap_dek_for_recipient.restype = ctypes.c_int

        self._lib.ciris_verify_unwrap_dek.argtypes = [
            ctypes.POINTER(ctypes.c_uint8),                    # recipient_priv[32]
            ctypes.POINTER(ctypes.c_uint8),                    # wrap_json
            ctypes.c_size_t,                                   # wrap_json_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),    # result_out
            ctypes.POINTER(ctypes.c_size_t),                   # result_len_out
        ]
        self._lib.ciris_verify_unwrap_dek.restype = ctypes.c_int

        self._has_key_grant_support = True
    except AttributeError:
        self._has_key_grant_support = False


def _wrap_dek_for_recipient(
    self: Any,
    recipient_x_pub: bytes,
    dek: bytes,
) -> Dict[str, bytes]:
    """Wrap a 32-byte DEK for a recipient X25519 public key.

    Per CIRISNodeCore MEDIA_SHARING.md §6.3 v4.4.0+ ``wrap_algorithm:
    v1`` = ``x25519-aes256-gcm-hkdf-sha256``. Generates a fresh
    ephemeral X25519 keypair per call, ECDHs against
    ``recipient_x_pub``, HKDF-SHA256-derives a wrap_key salt-bound to
    both pubkeys (closes UKS), and AES-256-GCM-seals the DEK under a
    fresh nonce.

    Args:
        recipient_x_pub: Recipient's 32-byte X25519 public key.
        dek: The 32-byte data-encryption-key being wrapped.

    Returns:
        Dict with keys:
        - ``ephemeral_public_key``: 32 bytes
        - ``nonce``: 12 bytes
        - ``ciphertext``: 48 bytes (32B DEK + 16B AES-GCM tag)

    Raises:
        CIRISVerifyError: If the library is older than v4.7.0 (no
            symbol), inputs are wrong-sized, or the FFI returns a
            non-success status code.
    """
    if not getattr(self, "_has_key_grant_support", False):
        raise CIRISVerifyError(
            "key_grant wheel surface unavailable — library is older "
            "than v4.7.0 or was built without the `key-grant` feature."
        )
    if not isinstance(recipient_x_pub, (bytes, bytearray)) or len(recipient_x_pub) != 32:
        raise CIRISVerifyError(
            f"recipient_x_pub must be exactly 32 bytes, got "
            f"{type(recipient_x_pub).__name__} of length "
            f"{len(recipient_x_pub) if hasattr(recipient_x_pub, '__len__') else '?'}"
        )
    if not isinstance(dek, (bytes, bytearray)) or len(dek) != 32:
        raise CIRISVerifyError(
            f"dek must be exactly 32 bytes, got "
            f"{type(dek).__name__} of length "
            f"{len(dek) if hasattr(dek, '__len__') else '?'}"
        )

    recipient_pub_buf = (ctypes.c_uint8 * 32).from_buffer_copy(bytes(recipient_x_pub))
    dek_buf = (ctypes.c_uint8 * 32).from_buffer_copy(bytes(dek))

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()

    ret = self._lib.ciris_verify_wrap_dek_for_recipient(
        recipient_pub_buf,
        dek_buf,
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        raise CIRISVerifyError(
            f"ciris_verify_wrap_dek_for_recipient FFI returned {ret}"
        )

    try:
        data = ctypes.string_at(result_ptr, result_len.value)
        self._lib.ciris_verify_free(result_ptr)
    except Exception as exc:  # noqa: BLE001 — defensive
        raise CIRISVerifyError(f"failed to read wrap result bytes: {exc}") from exc

    try:
        wrap_json: Dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as exc:
        raise CIRISVerifyError(f"wrap output is not valid JSON: {exc}") from exc

    # The Rust side serializes [u8; N] arrays as JSON int arrays.
    # Convert each to bytes for the Python boundary contract — the
    # wheel surface is bytes-shaped, not int-array-shaped.
    return {
        "ephemeral_public_key": bytes(wrap_json["ephemeral_public_key"]),
        "nonce": bytes(wrap_json["nonce"]),
        "ciphertext": bytes(wrap_json["ciphertext"]),
    }


def _unwrap_dek(
    self: Any,
    recipient_x_priv: bytes,
    wrap: Dict[str, Any],
) -> bytes:
    """Unwrap a 32-byte DEK from a ``KeyGrantWrap``-shaped dict.

    Args:
        recipient_x_priv: Recipient's 32-byte X25519 private key.
        wrap: Dict matching the shape returned by
            :func:`wrap_dek_for_recipient`. Either ``bytes`` values
            or JSON-int-array values are accepted (the latter for
            round-tripping through a JSON envelope).

    Returns:
        The 32-byte DEK.

    Raises:
        CIRISVerifyError: With message starting ``"WRAP_UNVERIFIED"``
            on the opaque AEAD-failure case (wrong recipient key,
            tampered ciphertext, swapped ephemeral_public_key, or
            tampered nonce — deliberately undistinguished per the
            AEAD opaque-failure discipline). Also raised if the
            library is older than v4.7.0 or the FFI returns a
            non-success status code.
    """
    if not getattr(self, "_has_key_grant_support", False):
        raise CIRISVerifyError(
            "key_grant wheel surface unavailable — library is older "
            "than v4.7.0 or was built without the `key-grant` feature."
        )
    if not isinstance(recipient_x_priv, (bytes, bytearray)) or len(recipient_x_priv) != 32:
        raise CIRISVerifyError(
            f"recipient_x_priv must be exactly 32 bytes, got "
            f"{type(recipient_x_priv).__name__} of length "
            f"{len(recipient_x_priv) if hasattr(recipient_x_priv, '__len__') else '?'}"
        )
    if not isinstance(wrap, dict):
        raise CIRISVerifyError(
            f"wrap must be a dict with `ephemeral_public_key`, `nonce`, "
            f"`ciphertext` keys; got {type(wrap).__name__}"
        )

    # Normalize wrap fields to JSON-serializable list-of-int form
    # (matches the KeyGrantWrap serde shape). The Rust side accepts
    # both representations because serde for `[u8; N]` reads either,
    # but we canonicalize here for shape clarity.
    def _to_int_list(field: str, expected_len: Optional[int]) -> list:
        v = wrap.get(field)
        if v is None:
            raise CIRISVerifyError(f"wrap missing required field `{field}`")
        if isinstance(v, (bytes, bytearray)):
            out = list(v)
        elif isinstance(v, list):
            out = v
        else:
            raise CIRISVerifyError(
                f"wrap[{field!r}] must be bytes or list-of-int, got "
                f"{type(v).__name__}"
            )
        if expected_len is not None and len(out) != expected_len:
            raise CIRISVerifyError(
                f"wrap[{field!r}] must be exactly {expected_len} bytes, "
                f"got {len(out)}"
            )
        return out

    wrap_normalized = {
        "ephemeral_public_key": _to_int_list("ephemeral_public_key", 32),
        "nonce": _to_int_list("nonce", 12),
        "ciphertext": _to_int_list("ciphertext", None),
    }
    wrap_json_bytes = json.dumps(wrap_normalized).encode("utf-8")
    wrap_json_buf = (ctypes.c_uint8 * len(wrap_json_bytes)).from_buffer_copy(wrap_json_bytes)
    priv_buf = (ctypes.c_uint8 * 32).from_buffer_copy(bytes(recipient_x_priv))

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()

    ret = self._lib.ciris_verify_unwrap_dek(
        priv_buf,
        wrap_json_buf,
        len(wrap_json_bytes),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        raise CIRISVerifyError(
            f"ciris_verify_unwrap_dek FFI returned {ret}"
        )

    try:
        data = ctypes.string_at(result_ptr, result_len.value)
        self._lib.ciris_verify_free(result_ptr)
    except Exception as exc:  # noqa: BLE001 — defensive
        raise CIRISVerifyError(f"failed to read unwrap result bytes: {exc}") from exc

    try:
        env: Dict[str, Any] = json.loads(data)
    except json.JSONDecodeError as exc:
        raise CIRISVerifyError(f"unwrap output is not valid JSON: {exc}") from exc

    # Opaque-failure envelope path: Rust returned Success at the FFI
    # layer with an `error` field carrying the AEAD failure mode.
    if "error" in env:
        code = env["error"].get("code", "UNKNOWN")
        message = env["error"].get("message", "")
        raise CIRISVerifyError(f"{code}: {message}")

    if "dek" not in env:
        raise CIRISVerifyError(
            f"unwrap success envelope missing `dek` field: keys={list(env.keys())}"
        )

    dek_field = env["dek"]
    if not isinstance(dek_field, list) or len(dek_field) != 32:
        raise CIRISVerifyError(
            f"unwrap success envelope `dek` must be 32-int list, got "
            f"{type(dek_field).__name__} of length "
            f"{len(dek_field) if hasattr(dek_field, '__len__') else '?'}"
        )
    return bytes(dek_field)


def attach_to(cls: type) -> type:
    """Attach the key-grant wheel surface to a ``CIRISVerify`` class.

    Patches ``cls.__init__`` to call ``_wire_key_grant_ffi`` at the
    end of the original ``__init__`` body (so the library handle
    exists before we look up its symbols), and adds the
    ``wrap_dek_for_recipient`` / ``unwrap_dek`` methods.

    Idempotent — calling twice is a no-op (the second call sees the
    sentinel attribute and returns the class unchanged).

    Args:
        cls: The :class:`ciris_verify.CIRISVerify` class.

    Returns:
        The same class, for chaining.
    """
    if getattr(cls, "_key_grant_wheel_attached", False):
        return cls

    original_init = cls.__init__

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        # Library is loaded by now; safely look up the FFI symbols.
        _wire_key_grant_ffi(self)

    cls.__init__ = __init__  # type: ignore[method-assign]
    cls.wrap_dek_for_recipient = _wrap_dek_for_recipient  # type: ignore[attr-defined]
    cls.unwrap_dek = _unwrap_dek  # type: ignore[attr-defined]
    cls._key_grant_wheel_attached = True  # type: ignore[attr-defined]
    return cls
