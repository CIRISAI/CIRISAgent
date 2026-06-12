"""
Federation peer-bootstrap routes (NodeCode share + add).

These endpoints let a user export a shareable code for their own agent's
federation identity (``GET /v1/system/peers/my-node-code``) and consume
one someone else shared (``POST /v1/system/peers/add-from-code``).
Added peers land in ``LocalPeerState`` as organic peers at
``trust=UNKNOWN`` (CIRISEdge#46) — verification before promoting to
TRUSTED is a separate flow (SAS, CIRISEdge#47).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import JSONResponse

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_observer, require_system_admin
from ciris_engine.logic.runtime.bootstrap_peers import BootstrapPeerSeeder
from ciris_engine.logic.utils.node_code_codec import (
    ChecksumMismatchError,
    InvalidVersionError,
    MalformedNodeCodeError,
    decode_node_code,
    encode_node_code,
    encode_qr_payload,
)
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.node_code import (
    NodeCode,
    NodeCodeAddRequest,
    NodeCodeAddResponse,
    NodeCodeShareResponse,
)

logger = logging.getLogger(__name__)

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]
AuthSystemAdminDep = Annotated[AuthContext, Depends(require_system_admin)]

router = APIRouter()

# Cached seeder per app instance. The seeder itself is stateless beyond
# its asyncio lock and ``time_service`` handle, so one instance per
# process is sufficient and avoids the cost of re-instantiating on each
# request. Stored on the request's app.state so the test client can
# inject a different seeder via app.state.bootstrap_peer_seeder.
_SEEDER_STATE_KEY = "bootstrap_peer_seeder"


def _get_or_create_seeder(request: Request) -> BootstrapPeerSeeder:
    """Resolve the BootstrapPeerSeeder from app.state, creating one if needed.

    Tests can pre-populate ``request.app.state.bootstrap_peer_seeder`` to
    inject a custom seeder. In production it is created lazily on first
    use, bound to whichever ``time_service`` is wired onto app.state.
    """
    existing = getattr(request.app.state, _SEEDER_STATE_KEY, None)
    if existing is not None:
        # `getattr` returns Any; narrow to the declared return type so
        # mypy's [no-any-return] check is satisfied without changing
        # runtime behavior.
        assert isinstance(existing, BootstrapPeerSeeder)
        return existing

    time_service = getattr(request.app.state, "time_service", None)
    if time_service is None:
        # The seeder needs a TimeServiceProtocol. We don't want to half-
        # construct one — surface this as a 503-ish error to the route.
        raise RuntimeError("Cannot create BootstrapPeerSeeder: time_service not wired on app.state")

    seeder = BootstrapPeerSeeder(time_service=time_service, registry_fetch_url=None)
    setattr(request.app.state, _SEEDER_STATE_KEY, seeder)
    return seeder


def _get_local_identity(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Return ``(key_id, pubkey_ed25519_base64)`` for the local agent.

    Reads via the same path the audit/authentication subsystems use:
    CIRISVerify ``get_ed25519_public_key_sync()``. Key id is derived
    from the pubkey fingerprint (``agent-{sha256(pubkey)[:12]}``) unless
    ``CIRIS_AGENT_ID`` overrides it.

    Allows tests to short-circuit by setting
    ``request.app.state.local_identity = (key_id, pubkey_b64)``. Returns
    ``(None, None)`` if the verifier is not yet available.
    """
    test_override = getattr(request.app.state, "local_identity", None)
    if test_override is not None:
        key_id, pubkey_b64 = test_override
        return key_id, pubkey_b64

    try:
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        verifier = get_verifier()
    except Exception as exc:
        logger.debug("CIRISVerify not available for NodeCode share: %s", exc)
        return None, None

    if not hasattr(verifier, "get_ed25519_public_key_sync"):
        logger.debug("CIRISVerify lacks get_ed25519_public_key_sync; cannot share NodeCode")
        return None, None

    try:
        pubkey_bytes = verifier.get_ed25519_public_key_sync()
    except Exception as exc:
        logger.debug("CIRISVerify get_ed25519_public_key_sync raised: %s", exc)
        return None, None

    if not pubkey_bytes:
        return None, None

    pubkey_b64 = base64.b64encode(pubkey_bytes).decode("ascii")

    agent_id_env = os.environ.get("CIRIS_AGENT_ID")
    if agent_id_env:
        key_id = f"agent-{agent_id_env}"
    else:
        fingerprint = hashlib.sha256(pubkey_bytes).hexdigest()[:12]
        key_id = f"agent-{fingerprint}"

    return key_id, pubkey_b64


@router.get(
    "/peers/my-node-code",
    responses={
        503: {"description": "Local federation identity is not yet available"},
    },
)
async def get_my_node_code(
    request: Request,
    auth: AuthObserverDep,
    transport_hint: Optional[str] = Query(
        None,
        description=(
            "Optional transport hint to embed in the code (e.g. 'tcp://agents.ciris.ai:4242'). "
            "Capped at 255 UTF-8 bytes."
        ),
    ),
    alias_hint: Optional[str] = Query(
        None,
        description="Optional display name for this agent to embed in the code. Capped at 255 UTF-8 bytes.",
    ),
) -> Any:
    """Return a shareable NodeCode for the local agent's federation identity.

    OBSERVER+ readable. The returned code is a round-trippable
    ``CIRIS-V1-...`` string carrying the agent's ``key_id`` and
    Ed25519 pubkey plus the (optional) transport / alias hints.
    """
    key_id, pubkey_b64 = _get_local_identity(request)
    if not key_id or not pubkey_b64:
        return JSONResponse(
            status_code=503,
            content={
                "error": "FEDERATION_IDENTITY_UNAVAILABLE",
                "detail": "Local agent's signing key is not yet available — CIRISVerify has not finished bootstrap.",
            },
        )

    try:
        node_code = NodeCode(
            key_id=key_id,
            pubkey_ed25519_base64=pubkey_b64,
            transport_hint=transport_hint,
            alias_hint=alias_hint,
        )
        code = encode_node_code(node_code)
        qr = encode_qr_payload(node_code)
    except MalformedNodeCodeError as exc:
        # Hint was over-length or pubkey was malformed.
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_NODE_CODE_INPUT", "detail": str(exc)},
        )

    response = NodeCodeShareResponse(
        code=code,
        qr_payload=qr,
        key_id=key_id,
        alias_hint=alias_hint,
    )
    return SuccessResponse(data=response)


@router.get(
    "/peers/federation-identity",
    responses={
        503: {"description": "Persist engine / federation identity not yet available"},
    },
)
async def get_federation_identity(request: Request, auth: AuthObserverDep) -> Any:
    """Return this occurrence's full federation identity aggregate.

    OBSERVER+ readable. Sources persist's ``local_identity_aggregate()``
    (persist 5.4.0+, CIRISPersist#198 / CEG 1.0 §5.6.8.8.2) — the
    single-call snapshot of the hybrid identity across the three keypair
    roles (signing Ed25519 + optional ML-DSA-65, Reticulum transport
    keys, content-encryption X25519 + ML-KEM-768). This is THE address
    the production lens / registry servers use to reach this node, shown
    in the UI alongside the NodeCode connect card.
    """
    try:
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            raise RuntimeError("persist engine not wired")
        import json as _json

        aggregate = _json.loads(engine.local_identity_aggregate())
    except Exception as exc:
        logger.debug("federation identity aggregate unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "FEDERATION_IDENTITY_UNAVAILABLE",
                "detail": f"persist local_identity_aggregate unavailable: {type(exc).__name__}",
            },
        )

    # Companion NodeCode identity (the connect-card key) so the UI can
    # render both on one surface.
    key_id, pubkey_b64 = _get_local_identity(request)
    return SuccessResponse(
        data={
            "aggregate": aggregate,
            "node_code_key_id": key_id,
            "node_code_pubkey_ed25519_base64": pubkey_b64,
        }
    )


def _decode_error_subtype(exc: Exception) -> str:
    if isinstance(exc, ChecksumMismatchError):
        return "CHECKSUM_MISMATCH"
    if isinstance(exc, InvalidVersionError):
        return "INVALID_VERSION"
    return "MALFORMED"


@router.post(
    "/peers/add-from-code",
    responses={
        400: {"description": "NodeCode is malformed, bad checksum, or wrong version"},
        409: {"description": "Known peer with different pubkey — anti-key-swap protection"},
        503: {"description": "Bootstrap-peer seeder is not yet wired"},
    },
)
async def add_peer_from_code(
    request: Request,
    payload: NodeCodeAddRequest,
    auth: AuthSystemAdminDep,
) -> Any:
    """Add a peer from a NodeCode string. SYSTEM_ADMIN only.

    Decodes the code, looks up any existing local state for the peer,
    and either records a new organic peer (``trust=UNKNOWN``) or
    refreshes the ``last_seen`` of the existing entry. Returns the
    resulting ``LocalPeerState`` plus a ``was_already_present`` boolean.

    Anti-key-swap: if a row already exists for ``key_id`` and its
    persisted ``pubkey_ed25519_base64`` does not match the one in the
    NodeCode, the call is rejected with 409 and no state is mutated.
    """
    try:
        node_code = decode_node_code(payload.code)
    except (ChecksumMismatchError, InvalidVersionError, MalformedNodeCodeError) as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_NODE_CODE",
                "subtype": _decode_error_subtype(exc),
                "detail": str(exc),
            },
        )

    try:
        seeder = _get_or_create_seeder(request)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "BOOTSTRAP_SEEDER_UNAVAILABLE", "detail": str(exc)},
        )

    # Anti-key-swap: if a row already exists for this key_id (canonical
    # or organic), verify its stored pubkey matches. The seeder's
    # ``record_organic_peer`` will silently preserve the existing
    # pubkey, so we must enforce this BEFORE calling into it — that
    # way the caller learns about the conflict instead of believing the
    # rebind succeeded.
    existing_state = seeder.get_local_state(node_code.key_id)
    was_already_present = existing_state is not None
    if existing_state is not None and existing_state.pubkey_ed25519_base64 != node_code.pubkey_ed25519_base64:
        return JSONResponse(
            status_code=409,
            content={
                "error": "PUBKEY_CONFLICT",
                "key_id": node_code.key_id,
                "existing_pubkey": existing_state.pubkey_ed25519_base64,
                "supplied_pubkey": node_code.pubkey_ed25519_base64,
                "detail": (
                    "A peer with this key_id already exists locally with a different "
                    "pubkey. Refusing silent rotation — confirm out-of-band before "
                    "removing the existing entry."
                ),
            },
        )

    try:
        peer_state = await seeder.record_organic_peer(
            key_id=node_code.key_id,
            pubkey_ed25519_base64=node_code.pubkey_ed25519_base64,
            alias=node_code.alias_hint,
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_NODE_CODE", "subtype": "MALFORMED", "detail": str(exc)},
        )

    return SuccessResponse(
        data=NodeCodeAddResponse(peer=peer_state, was_already_present=was_already_present),
    )
