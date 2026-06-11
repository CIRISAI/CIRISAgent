"""Operational-data admission — Python binding (CIRISVerify#65, v5.1.0+).

Exposes :func:`resolve_role_authority` and
:func:`verify_partner_record_quorum`, thin wrappers over the FFI symbols
``ciris_verify_resolve_role_authority`` and
``ciris_verify_partner_record_quorum`` which call
``ciris_verify_core::operational_admit`` — the CEG 1.0-RC2 §5.6.8.13
admit-verification surface (CIRISRegistry#70).

There is exactly one blessed implementation of each check; the wheel
reaches it rather than reimplementing the role-chain walk or the
steward-quorum count (RC2 §5.6.8.13 forbids a third bespoke path). Both
functions are pure evaluators — no I/O — and **fail-closed**: a negative
admission is a successful call returning ``authorized``/``admitted`` =
``False``, never an exception.
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Any, Optional

__all__ = ["resolve_role_authority", "verify_partner_record_quorum"]

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
                _wire(lib.ciris_verify_resolve_role_authority)
                _wire(lib.ciris_verify_partner_record_quorum)
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
            lib.ciris_verify_free.restype = None
            _lib = lib
            return _lib
    raise RuntimeError(
        "operational-admit FFI symbols not available — could not load the "
        f"CIRISVerify shared library (last error: {last_err}). The library "
        "must be built with the wheel (>= v5.1.0)."
    )


def _call(symbol: str, request: dict) -> dict:
    lib = _load_lib()
    fn = getattr(lib, symbol)
    body = _json.dumps(request, ensure_ascii=False).encode("utf-8")
    out_ptr = ctypes.POINTER(ctypes.c_ubyte)()
    out_len = ctypes.c_size_t(0)
    rc = fn(body, len(body), ctypes.byref(out_ptr), ctypes.byref(out_len))
    if rc != _SUCCESS:
        raise ValueError(
            f"{symbol}: malformed request (FFI code {rc}) — this is a caller "
            "error, distinct from a fail-closed negative verdict"
        )
    n = out_len.value
    if n == 0:
        return {}
    try:
        raw = ctypes.string_at(out_ptr, n)
    finally:
        lib.ciris_verify_free(ctypes.cast(out_ptr, ctypes.c_void_p))
    return _json.loads(raw)


def resolve_role_authority(
    actor_key_id: str,
    org_id: str,
    required_role: str,
    current_memberships: list[dict],
    key_directory: list[dict],
    root_stewards: list[str],
) -> dict:
    """Resolve ``organization`` / ``org_membership`` role-gated admission
    (CEG 1.0-RC2 §5.6.8.13, the §8.1.12.7.1 ``delegates_to`` resolver).

    Args:
        actor_key_id: the key that signed the operation being admitted.
        org_id: the target organization id.
        required_role: ``"org_admin"`` | ``"key_manager"`` | ``"operator"``
            | ``"viewer"``.
        current_memberships: caller-resolved *current state* — the latest
            non-superseded/non-withdrawn ``org_membership`` grants for this
            org. Each: ``{"signed_envelope": {...},
            "ed25519_signature_base64": "...",
            "mldsa65_signature_base64": "..."}``. The signed envelope MUST
            carry ``user_id`` / ``org_id`` / ``role`` / ``status`` /
            ``attesting_key_id``.
        key_directory: pinned hybrid pubkeys per key_id (from
            ``federation_keys``). Each: ``{"member_id": "...",
            "ed25519_public_key_base64": "...",
            "mldsa65_public_key_base64": "..."}``.
        root_stewards: key_ids recognized as org-creation root authority.

    Returns:
        ``{"authorized": bool, "established_by": str|None,
        "root_anchored": bool, "reason": str}``. Fail-closed: any
        ambiguity yields ``authorized: False``.

    Raises:
        ValueError: the request itself is malformed (a caller error, NOT a
            negative verdict).
        RuntimeError: the shared library / FFI symbols are unavailable.
    """
    return _call(
        "ciris_verify_resolve_role_authority",
        {
            "actor_key_id": actor_key_id,
            "org_id": org_id,
            "required_role": required_role,
            "current_memberships": current_memberships,
            "key_directory": key_directory,
            "root_stewards": root_stewards,
        },
    )


def verify_partner_record_quorum(
    partner_record: Any,
    steward_roster: list[dict],
    signatures: list[dict],
    threshold: int,
) -> dict:
    """Verify the ``partner_record`` M-of-N steward quorum (CEG 1.0-RC2
    §5.6.8.13 / §5.6.8.10; CIRISVerify#31).

    Set-semantics arrays in ``partner_record`` (``capabilities_granted``
    etc.) MUST already be lexicographically sorted (§0.9.2.1 rule 1) — JCS
    preserves array order, so the M stewards must converge on identical
    canonical bytes *before* the quorum can evaluate.

    Args:
        partner_record: the signed envelope (a JSON-able value).
        steward_roster: the N stewards (``role: "founder"``), same entry
            shape as ``key_directory`` above plus the role.
        signatures: the submitted signature set — each ``{"member_id":
            "...", "ed25519_signature_base64": "...",
            "mldsa65_signature_base64": "..."}``.
        threshold: M (the minimum distinct valid steward signatures).

    Returns:
        ``{"admitted": bool, "valid_count": int, "error": str?}``.
        Fail-closed: an unmet quorum is ``admitted: False`` with a reason,
        not an exception.

    Raises:
        ValueError: the request itself is malformed.
        RuntimeError: the shared library / FFI symbols are unavailable.
    """
    return _call(
        "ciris_verify_partner_record_quorum",
        {
            "partner_record": partner_record,
            "steward_roster": steward_roster,
            "signatures": signatures,
            "threshold": threshold,
        },
    )
