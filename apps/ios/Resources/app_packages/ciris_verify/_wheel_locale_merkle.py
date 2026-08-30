"""Per-locale Merkle root + inclusion-proof — Python wheel surface
(CIRISVerify#50, v4.7.0+).

Exposes the v3.9.0 [`merkle_root`] and [`verify_locale_inclusion`]
Rust entrypoints to wheel consumers so federation peers can drive
RFC 6962 Merkle composition + inclusion verification for the
``provenance:build_manifest:{target}`` per-locale sub-tree from
Python.

See ``src/ciris-verify-ffi/src/wheel_locale_merkle.rs`` for the
underlying FFI surface this module wraps, and
``src/ciris-verify-core/src/locale_merkle.rs`` for the leaf-hash and
inclusion-proof discipline.

## Wire shape

- :meth:`locale_merkle_root` takes ``leaves: list[bytes]`` (each leaf
  is 32 bytes) and returns the 32-byte root as ``bytes``.

- :meth:`verify_locale_inclusion` takes:
  - ``leaf``: ``LocaleLeaf`` dict ({``target``, ``lang_code``,
    ``files_root``, ``build_id``, ``signer_identity``})
  - ``proof``: ``LocaleInclusionProof`` dict ({``leaf_hash``,
    ``lang_code``, ``sibling_hashes``, ``leaf_index``, ``tree_size``})
  - ``expected_root``: 32-byte ``bytes`` (NOT hex)

  Returns ``True`` on full inclusion-proof match;
  ``False`` on any mismatch (lang_code, leaf-hash, tree-size,
  sibling-count, reconstructed root). The diagnostic message from the
  FFI error envelope is logged via the standard ``logging`` module
  (logger name ``ciris_verify._wheel_locale_merkle``).

## Integration — ``attach_to(CIRISVerify)``

Loaded out-of-band so the FFI surface lives in its own file. Patches
``CIRISVerify`` in place to install two methods and add a
``_wire_locale_merkle_ffi`` instance method run from ``__init__``.

Sets ``self._has_locale_merkle_support = True/False`` based on FFI
symbol presence; older wheels are flagged ``False`` and method calls
return ``None`` instead of raising.
"""

from __future__ import annotations

import ctypes
import json
import logging
from typing import Optional


_LOG = logging.getLogger(__name__)

# Sentinel for attach_to idempotency.
_ATTACHED_MARKER = "_ciris_wheel_locale_merkle_attached"


# =============================================================================
# FFI wiring (per-instance)
# =============================================================================


def _wire_locale_merkle_ffi(self) -> None:
    """Wire ctypes argtypes/restype for the v4.7.0 locale-merkle FFI symbols.

    Sets ``self._has_locale_merkle_support`` to ``True`` if both
    symbols resolve, ``False`` otherwise.
    """
    try:
        self._lib.ciris_verify_locale_merkle_root.argtypes = [
            ctypes.c_char_p,                                  # leaves_json
            ctypes.c_size_t,                                  # leaves_len
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_locale_merkle_root.restype = ctypes.c_int

        self._lib.ciris_verify_locale_inclusion_verify.argtypes = [
            ctypes.c_char_p,                                  # leaf_json
            ctypes.c_size_t,                                  # leaf_len
            ctypes.c_char_p,                                  # proof_json
            ctypes.c_size_t,                                  # proof_len
            ctypes.c_char_p,                                  # expected_root (32 B)
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),   # result_out
            ctypes.POINTER(ctypes.c_size_t),                  # result_len_out
        ]
        self._lib.ciris_verify_locale_inclusion_verify.restype = ctypes.c_int

        self._has_locale_merkle_support = True
    except AttributeError:
        self._has_locale_merkle_support = False


# =============================================================================
# Helpers
# =============================================================================


def _leaves_to_json_bytes(leaves) -> bytes:
    """Normalize a ``list[bytes]`` of 32-byte leaves into the JSON
    ``[[u8; 32], ...]`` shape the FFI expects.

    Each leaf may be ``bytes``, ``bytearray``, or ``list[int]``;
    validation enforces 32 bytes per leaf.
    """
    normalized = []
    for i, leaf in enumerate(leaves):
        if isinstance(leaf, (bytes, bytearray)):
            arr = list(leaf)
        else:
            arr = list(leaf)
        if len(arr) != 32:
            raise ValueError(
                f"leaves[{i}] must be exactly 32 bytes (got {len(arr)})"
            )
        normalized.append(arr)
    return json.dumps(normalized).encode("utf-8")


# =============================================================================
# Methods grafted onto CIRISVerify
# =============================================================================


def locale_merkle_root(self, leaves) -> Optional[bytes]:
    """Compute the RFC 6962 Merkle root over a fully-built leaf set.

    Applies the §3.2.1.2 last-leaf-duplication padding convention for
    non-power-of-2 leaf counts (e.g. 29 → 32). Useful for testing
    and for callers that hold all leaves and want to produce the
    parent root.

    Args:
        leaves: ``list[bytes]`` — each entry is a 32-byte SHA-256
            leaf hash. Empty input is rejected.

    Returns:
        32-byte root as ``bytes``. ``None`` if the loaded wheel
        predates v4.7.0 (FFI symbol absent).

    Raises:
        ValueError: If ``leaves`` is empty or if any leaf is not
            exactly 32 bytes.
        RuntimeError: On non-zero FFI status (e.g. malformed JSON
            after normalization — should not occur).
    """
    if not getattr(self, "_has_locale_merkle_support", False):
        return None

    if not leaves:
        raise ValueError("leaves must be non-empty")

    leaves_json = _leaves_to_json_bytes(leaves)

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_locale_merkle_root(
        leaves_json,
        len(leaves_json),
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        raise RuntimeError(
            f"ciris_verify_locale_merkle_root failed with status {ret}"
        )

    try:
        data = ctypes.string_at(result_ptr, result_len.value)
    finally:
        self._lib.ciris_verify_free(result_ptr)

    payload = json.loads(data)
    return bytes(payload["root"])


def verify_locale_inclusion(
    self,
    leaf: dict,
    proof: dict,
    expected_root: bytes,
) -> Optional[bool]:
    """Verify a per-locale inclusion proof against the expected root.

    Walks the proof from leaf → root, reconstructs the claimed
    parent root, and compares against ``expected_root``. Returns
    ``True`` on full match.

    Args:
        leaf: ``LocaleLeaf`` dict — ``target``, ``lang_code``,
            ``files_root``, ``build_id``, ``signer_identity``.
        proof: ``LocaleInclusionProof`` dict — ``leaf_hash``,
            ``lang_code``, ``sibling_hashes``, ``leaf_index``,
            ``tree_size``. Hex fields accept optional ``sha256:``
            prefix.
        expected_root: 32 raw bytes (NOT hex) — the parent Merkle
            root from the steward-signed
            ``provenance:build_manifest:{target}`` attestation.

    Returns:
        ``True`` on successful inclusion-proof verification;
        ``False`` on any mismatch (the diagnostic message from the
        FFI error envelope is logged at WARNING).
        ``None`` if the loaded wheel predates v4.7.0 (FFI symbol absent).

    Raises:
        ValueError: If ``expected_root`` is not 32 bytes.
        RuntimeError: On non-zero FFI status.
    """
    if not getattr(self, "_has_locale_merkle_support", False):
        return None

    if not isinstance(expected_root, (bytes, bytearray)) or len(expected_root) != 32:
        raise ValueError(
            "expected_root must be exactly 32 bytes "
            f"(got {len(expected_root) if isinstance(expected_root, (bytes, bytearray)) else type(expected_root).__name__})"
        )

    leaf_bytes = json.dumps(leaf).encode("utf-8")
    proof_bytes = json.dumps(proof).encode("utf-8")
    root_buf = bytes(expected_root)

    result_ptr = ctypes.POINTER(ctypes.c_uint8)()
    result_len = ctypes.c_size_t()
    ret = self._lib.ciris_verify_locale_inclusion_verify(
        leaf_bytes,
        len(leaf_bytes),
        proof_bytes,
        len(proof_bytes),
        root_buf,
        ctypes.byref(result_ptr),
        ctypes.byref(result_len),
    )
    if ret != 0:
        raise RuntimeError(
            f"ciris_verify_locale_inclusion_verify failed with status {ret}"
        )

    try:
        data = ctypes.string_at(result_ptr, result_len.value)
    finally:
        self._lib.ciris_verify_free(result_ptr)

    payload = json.loads(data)
    verified = bool(payload.get("verified", False))
    if not verified:
        err = payload.get("error") or {}
        _LOG.warning(
            "locale inclusion proof rejected: code=%s message=%s",
            err.get("code"),
            err.get("message"),
        )
    return verified


# =============================================================================
# attach_to(cls) — mutates the CIRISVerify class in place
# =============================================================================


def attach_to(cls) -> None:
    """Graft the locale-merkle surface onto a ``CIRISVerify`` subclass.

    Adds :meth:`locale_merkle_root` and :meth:`verify_locale_inclusion`
    AND patches ``cls.__init__`` so per-instance ctypes wiring runs
    after ``_load_library`` populates ``self._lib``. Idempotent.

    Caller is responsible for invoking this exactly once during module
    import (e.g. from ``client.py``):

        from ._wheel_locale_merkle import attach_to as _attach_locale_merkle
        _attach_locale_merkle(CIRISVerify)
    """
    if getattr(cls, _ATTACHED_MARKER, False):
        return

    cls._wire_locale_merkle_ffi = _wire_locale_merkle_ffi
    cls.locale_merkle_root = locale_merkle_root
    cls.verify_locale_inclusion = verify_locale_inclusion

    original_init = cls.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if getattr(self, "_lib", None) is None:
            self._has_locale_merkle_support = False
            return
        self._wire_locale_merkle_ffi()

    patched_init.__wrapped__ = original_init  # for introspection
    cls.__init__ = patched_init

    setattr(cls, _ATTACHED_MARKER, True)
