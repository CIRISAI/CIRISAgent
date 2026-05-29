"""
NodeCode schemas — shareable peer-bootstrap codes (CIRISAgent 2.9.4).

A NodeCode is a compact, user-shareable encoding of a federation peer's
identity (key_id + pubkey + optional transport/alias hints) plus a
checksum. The encoded form is a string like

    CIRIS-V1-ABCD-EFGH-IJKL-...

that a receiver can type, paste, or scan (QR) to add the sender as an
organic peer (CIRISEdge#46 ``trust=UNKNOWN``). NodeCode is the BOOTSTRAP
UX; SAS verification (CIRISEdge#47) is the post-add verification step
that promotes UNKNOWN → TRUSTED.

These models are pure data carriers. The actual encode/decode lives in
``ciris_engine.logic.utils.node_code_codec`` so the schema package stays
dependency-free.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.canonical_peer import LocalPeerState


class NodeCode(BaseModel):
    """Decoded NodeCode payload.

    ``key_id`` is the human-readable Ed25519 ``signer_key_id`` of the
    peer (matches ``LocalPeerState.key_id`` and
    ``CanonicalBootstrapPeer.key_id``). The codec hashes it to 32 bytes
    when packing the binary payload — the original display form is
    preserved on round-trip via the trailing hint fields.

    ``pubkey_ed25519_base64`` is the same base64 string carried on
    ``LocalPeerState.pubkey_ed25519_base64`` (raw 32-byte Ed25519
    public key, base64 encoded). The codec decodes it to 32 raw bytes
    when packing.

    ``transport_hint`` and ``alias_hint`` are optional UTF-8 strings
    capped at 255 bytes each. They are not authoritative — Edge resolves
    real transports via its own discovery — but they let the receiver's
    UI show a useful display name and dialled address on first contact.
    """

    key_id: str = Field(
        ...,
        min_length=1,
        description="Ed25519 signer_key_id (display form) of the peer being shared.",
    )
    pubkey_ed25519_base64: str = Field(
        ...,
        min_length=1,
        description="Ed25519 public key, base64-encoded — matches LocalPeerState.pubkey_ed25519_base64.",
    )
    transport_hint: Optional[str] = Field(
        None,
        description="Optional transport hint, e.g. 'tcp://agents.ciris.ai:4242'. Max 255 UTF-8 bytes.",
    )
    alias_hint: Optional[str] = Field(
        None,
        description="Optional human-readable alias the sender suggests for themselves. Max 255 UTF-8 bytes.",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class NodeCodeShareResponse(BaseModel):
    """Response body for ``GET /v1/system/peers/my-node-code``.

    ``code`` is the dashed display form (``CIRIS-V1-ABCD-...``) and
    ``qr_payload`` is the same data without dashes — some QR generators
    prefer a continuous alphanumeric string.
    """

    code: str = Field(..., min_length=1, description="Full CIRIS-V1-... dashed form for display.")
    qr_payload: str = Field(
        ...,
        min_length=1,
        description="Same content as `code` but without separator dashes — for QR generators.",
    )
    key_id: str = Field(..., min_length=1, description="Local agent's federation key_id.")
    alias_hint: Optional[str] = Field(
        None,
        description="The alias hint embedded in the code, if the caller supplied one.",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class NodeCodeAddRequest(BaseModel):
    """Request body for ``POST /v1/system/peers/add-from-code``."""

    code: str = Field(
        ...,
        min_length=1,
        description="A CIRIS-V1-... NodeCode string. Whitespace and dashes are tolerated.",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class NodeCodeAddResponse(BaseModel):
    """Response body for ``POST /v1/system/peers/add-from-code``.

    Returns the resulting ``LocalPeerState`` (organic) plus an
    idempotency signal: ``was_already_present`` is true when the peer
    was already in local state at call time. Either case is success.
    """

    peer: LocalPeerState = Field(..., description="The organic peer state after the add.")
    was_already_present: bool = Field(
        ...,
        description="True if a row for this key_id already existed before the call.",
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")
