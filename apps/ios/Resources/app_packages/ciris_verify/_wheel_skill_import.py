"""SkillImportManifest verification — Python wheel surface
(CIRISVerify#50, v4.7.0+).

Exposes the v3.9.0 [`verify_skill_import_manifest`] Rust entrypoint to
wheel consumers so federation peers can drive CEG-0.2 §3.2.1.1 /
§5.2.1 community-skill import-provenance verification from Python.

See ``src/ciris-verify-ffi/src/wheel_skill_import.rs`` for the
underlying FFI surface this module wraps, and
``src/ciris-verify-core/src/skill_import.rs`` for the verification
logic.

## Wire shape

- Input ``manifest``: dict matching the
  ``SkillImportManifest`` serde shape:

  ```python
  {
      "source": "registry:ciris-registry-us",
      "skill_manifest_sha256": "<64-char lowercase hex>",
      "signer_identity": "registry-steward-us",
      "import_timestamp": "2026-05-28T17:30:00.000Z",
      "capability_declaration": ["domain:medical:triage", ...],
      "valid_until": "2026-08-28T17:30:00.000Z",  # optional
      "signature": {
          "classical": "<base64 Ed25519 sig>",
          "classical_algorithm": "ed25519",
          "pqc": "<base64 ML-DSA-65 sig>",
          "pqc_algorithm": "ml-dsa-65",
          "key_id": "registry-steward-us"
      }
  }
  ```

- Input ``trusted_pubkey``: dict carrying the steward pubkey:

  ```python
  {"ed25519": [..32 bytes..], "ml_dsa_65": [..bytes..]}
  ```

  Byte arrays may be either Python ``list[int]`` or ``bytes`` —
  ``json.dumps`` normalizes to a JSON array of ints. The Rust side
  leaks these into ``'static`` memory (one-time per distinct pubkey,
  see the FFI module docstring); callers should pass a small number
  of long-lived pubkey dicts, not a fresh dict per call.

- Return on success: the parsed manifest dict (round-trip — the same
  shape supplied as input, with normalized field ordering).

- Return on failure: raises :class:`~ciris_verify.exceptions.CIRISVerifyError`
  carrying the typed error code (``INVALID_PUBKEY_JSON``,
  ``INVALID_PUBKEY_SHAPE``, ``SIGNATURE_VERIFICATION_FAILED``) and
  message from the FFI envelope.

## Integration — ``attach_to(CIRISVerify)``

Loaded out-of-band so the FFI surface lives in its own file. Patches
``CIRISVerify`` in place to:

1. Install :meth:`verify_skill_import_manifest`.
2. Patch ``__init__`` so per-instance ctypes wiring runs at the end of
   construction (after ``_load_library`` populates ``self._lib``).

Sets ``self._has_skill_import_support = True/False`` based on FFI
symbol presence; older wheels are flagged ``False`` and method calls
return ``None`` instead of raising.
"""

from __future__ import annotations

import ctypes
import json
from typing import Optional


# Sentinel for attach_to idempotency.
_ATTACHED_MARKER = "_ciris_wheel_skill_import_attached"


# =============================================================================
# FFI wiring (per-instance)
# =============================================================================


def _wire_skill_import_ffi(self) -> None:
    """Wire ctypes argtypes/restype for the v4.7.0 skill-import FFI symbol.

    Sets ``self._has_skill_import_support`` to ``True`` if the symbol
    resolves, ``False`` otherwise. Older wheels (pre-v4.7.0) gracefully
    degrade.
    """
    try:
        self._lib.ciris_verify_skill_import_manifest_verify.argtypes = [
            ctypes.c_char_p,                                  # manifest_json
            ctypes.c_size_t,                                  # manifest_len
            ctypes.c_char_p,                                  # trusted_pubkey_json
            ctypes.c_size_t,                                  # trusted_pubkey_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_skill_import_manifest_verify.restype = ctypes.c_int
        self._has_skill_import_support = True
    except AttributeError:
        self._has_skill_import_support = False


# =============================================================================
# Helpers
# =============================================================================


def _normalize_bytes_field(value) -> list:
    """Convert bytes / bytearray / list[int] → list[int] for JSON.

    ``json.dumps`` cannot serialize ``bytes`` directly. Callers may
    pass either ``bytes`` or ``list[int]``; both are normalized here.
    """
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    return list(value)


# =============================================================================
# Method grafted onto CIRISVerify
# =============================================================================


def verify_skill_import_manifest(
    self,
    manifest: dict,
    trusted_pubkey: dict,
) -> Optional[dict]:
    """Verify a ``SkillImportManifest`` against a trusted steward pubkey.

    Drives the v3.9.0 / v4.0.0 CEG-0.2 §3.2.1.1 / §5.2.1 verification
    path: canonical-bytes reconstruction, §0.5 RFC 3339 timestamp
    discipline, §0.6 lowercase-hex discipline, and hybrid Ed25519 +
    ML-DSA-65 signature verification over the canonical bytes.

    Args:
        manifest: ``SkillImportManifest`` dict (see module docstring
            for the field shape).
        trusted_pubkey: ``{"ed25519": [..32 bytes..], "ml_dsa_65":
            [..bytes..]}`` — the steward pubkey to verify against.
            ``bytes`` and ``list[int]`` are both accepted for the
            inner byte arrays.

    Returns:
        Parsed manifest dict on success (round-trip). ``None`` if the
        loaded wheel predates v4.7.0 (FFI symbol absent).

    Raises:
        CIRISVerifyError: On any verification failure, carrying the
            typed FFI error code (``INVALID_PUBKEY_JSON``,
            ``INVALID_PUBKEY_SHAPE``, ``SIGNATURE_VERIFICATION_FAILED``)
            and the upstream message.

    Note:
        **Caller selects ``trusted_pubkey`` by source-type.** This
        method does not route key selection based on the manifest's
        ``source`` prefix — picking which steward key to verify
        against is consumer policy. See
        ``src/ciris-verify-core/src/skill_import.rs`` for the source-
        type discrimination contract.
    """
    if not getattr(self, "_has_skill_import_support", False):
        return None

    manifest_bytes = json.dumps(manifest).encode("utf-8")

    # Normalize bytes fields so json.dumps doesn't choke on raw bytes
    # for the pubkey byte arrays.
    pubkey_normalized = {
        "ed25519": _normalize_bytes_field(trusted_pubkey["ed25519"]),
        "ml_dsa_65": _normalize_bytes_field(trusted_pubkey["ml_dsa_65"]),
    }
    pubkey_bytes = json.dumps(pubkey_normalized).encode("utf-8")

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_skill_import_manifest_verify(
        manifest_bytes,
        len(manifest_bytes),
        pubkey_bytes,
        len(pubkey_bytes),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )

    # Non-zero status: hard FFI failure (null input, OOM, panic). The
    # body is undefined in this case; surface as a CIRISVerifyError so
    # the caller can distinguish from a soft signature-fail.
    if ret != 0:
        from .exceptions import CIRISVerifyError
        raise CIRISVerifyError(
            f"ciris_verify_skill_import_manifest_verify FFI failed with status {ret}"
        )

    try:
        data = ctypes.string_at(result_ptr, result_len.value)
    finally:
        self._lib.ciris_verify_free(result_ptr)

    payload = json.loads(data)

    # Error envelope path — the FFI succeeded but the verification
    # returned a typed error. Raise CIRISVerifyError carrying the code.
    if isinstance(payload, dict) and "error" in payload:
        from .exceptions import CIRISVerifyError
        err = payload["error"]
        raise CIRISVerifyError(
            f"{err.get('code', 'UNKNOWN')}: {err.get('message', '')}"
        )

    return payload


# =============================================================================
# attach_to(cls) — mutates the CIRISVerify class in place
# =============================================================================


def attach_to(cls) -> None:
    """Graft the SkillImportManifest verifier onto a ``CIRISVerify`` subclass.

    Adds :meth:`verify_skill_import_manifest` AND patches
    ``cls.__init__`` so per-instance ctypes wiring runs after
    ``_load_library`` populates ``self._lib``. Idempotent.

    Caller is responsible for invoking this exactly once during module
    import (e.g. from ``client.py``):

        from ._wheel_skill_import import attach_to as _attach_skill_import
        _attach_skill_import(CIRISVerify)
    """
    if getattr(cls, _ATTACHED_MARKER, False):
        return

    cls._wire_skill_import_ffi = _wire_skill_import_ffi
    cls.verify_skill_import_manifest = verify_skill_import_manifest

    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if getattr(self, "_lib", None) is None:
            self._has_skill_import_support = False
            return
        self._wire_skill_import_ffi()

    patched_init.__wrapped__ = original_init  # for introspection
    cls.__init__ = patched_init

    setattr(cls, _ATTACHED_MARKER, True)
