"""Build-manifest Contribution verification — Python binding
(CIRISVerify#25, v6.2.0+).

Exposes :func:`verify_build_manifest_contribution`, a thin wrapper over the FFI
symbol ``ciris_verify_build_manifest_contribution`` which calls
``ciris_verify_core::manifest_contribution`` — the **consumer** of the
pipeline-as-delegated-attester model.

A CI pipeline holds a ``node`` identity; an accountable human grants it
``delegates_to(human → pipeline, infra:attest)`` ("publish manifests on my
behalf"); the pipeline signs each build manifest as that human's delegate. This
function runs the full authority walk a consumer (CIRISServer's outbox drain,
registry tooling) must run before trusting a build: pipeline signature → the
human's delegation grant → the §1.3 infra/agency scope split → the
"builders I trust" decision. There is one blessed implementation; the wheel
reaches it rather than reimplementing the chain walk.

**Fail-closed:** a rejection is a successful call returning ``trusted: False``
with a ``reason``, never an exception. Only a malformed request raises.
"""

from __future__ import annotations

import ctypes
import json as _json
import platform as _platform
import threading as _threading
from pathlib import Path
from typing import Any, Optional

__all__ = ["verify_build_manifest_contribution"]

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
                _wire(lib.ciris_verify_build_manifest_contribution)
            except (OSError, AttributeError) as exc:
                last_err = exc
                continue
            lib.ciris_verify_free.argtypes = [ctypes.c_void_p]
            lib.ciris_verify_free.restype = None
            _lib = lib
            return _lib
    raise RuntimeError(
        "manifest-contribution FFI symbol not available — could not load the "
        f"CIRISVerify shared library (last error: {last_err}). The library "
        "must be built with the wheel (>= v6.2.0)."
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


def verify_build_manifest_contribution(
    obj: Any,
    pipeline_member: dict,
    grant: dict,
    granter_member: dict,
    trusted_build_authorities: Optional[list[str]] = None,
) -> dict:
    """Verify a build-manifest Contribution end-to-end (CIRISVerify#25).

    The full chain, all fail-closed: the pipeline's bound-hybrid signature
    verifies against its pinned pubkeys; the Contribution carries
    ``delegation_scope: infra:attest`` and a ``dimension`` matching its own
    ``build.target``; the human's ``delegates_to`` grant verifies against the
    pinned granter pubkeys, delegates to *this* pipeline, and carries
    ``infra:attest``; the scope set passes the §1.3 node infra/agency split; and
    the ``on_behalf_of`` human is in ``trusted_build_authorities``.

    Args:
        obj: the ``build_manifest_contribution`` object as drained from the CEG
            outbox (a JSON-able ``SignedCegObject``).
        pipeline_member: the pipeline ``node``'s pinned pubkeys —
            ``{"member_id": ..., "ed25519_public_key_base64": ...,
            "mldsa65_public_key_base64": ...}``. Resolve this from your key
            directory by the object's ``attesting_key_id`` — never take it from
            the object (the identity-binding discipline; a forged grant under a
            human's key_id fails the binding).
        grant: the ``delegates_to(human → pipeline, infra:attest)`` grant —
            ``{"signed_envelope": {...}, "ed25519_signature_base64": ...,
            "mldsa65_signature_base64": ...}``.
        granter_member: the human granter's pinned pubkeys (same shape as
            ``pipeline_member``), resolved by the grant's ``attesting_key_id``.
        trusted_build_authorities: the trio's "builders I trust" set. Pass
            ``None``/``[]`` to verify the chain *without* the trust decision —
            useful to surface which human a build roots in before deciding.

    Returns:
        On trust: ``{"trusted": True, "attested_by": ..., "on_behalf_of": ...,
        "target": ..., "build_id": ..., "binary_hash": ...,
        "binary_version": ..., "manifest_hash": ...}``. On rejection:
        ``{"trusted": False, "reason": "..."}`` naming the first failing step.

    Raises:
        ValueError: the request itself is malformed (a caller error, NOT a
            negative verdict).
        RuntimeError: the shared library / FFI symbols are unavailable.
    """
    return _call(
        "ciris_verify_build_manifest_contribution",
        {
            "object": obj,
            "pipeline_member": pipeline_member,
            "grant": grant,
            "granter_member": granter_member,
            "trusted_build_authorities": trusted_build_authorities or [],
        },
    )
