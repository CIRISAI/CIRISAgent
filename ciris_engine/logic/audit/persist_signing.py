"""Shared helpers for persist-routed audit signing.

Used by both the A0b chain-bridge entry (tools/ops/audit_chain_bridge.py)
and the A3 GraphAuditService cutover. Single source of truth for:

  - resolving the agent's CIRISVerify-backed signing material
  - signing canonical bytes via the verifier
  - deriving the tenant_id under which persist records entries

Persist owns canonicalization (audit_canonicalize_for_hash +
audit_canonicalize_for_signing). The agent supplies the pubkey + signs the
canonical bytes; persist verifies the chain on read.
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional


def get_signer_material() -> tuple[bytes, str, str]:
    """Return (pubkey_bytes, actor_id_b64, signing_key_id) from CIRISVerify.

    CIRISVerify wraps the TPM-backed Ed25519 key when hardware is present,
    falling back to the software unified key otherwise. Either way, this
    is the agent's audit signing key — registered with persist's
    accord_public_keys directory via C3 so verifiers can resolve
    signing_key_id -> pubkey.

    The signing_key_id is prefixed `agent-` and uses CIRIS_AGENT_ID when
    set; otherwise falls back to a 12-char pubkey fingerprint so multiple
    agent occurrences on one host don't collide.
    """
    from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
        get_verifier,
    )

    verifier = get_verifier()
    if verifier is None or not hasattr(verifier, "get_ed25519_public_key_sync"):
        raise RuntimeError(
            "CIRISVerify verifier unavailable — cannot sign audit entries "
            "without the agent's signing key"
        )
    pubkey_bytes: bytes = verifier.get_ed25519_public_key_sync()
    if not pubkey_bytes:
        raise RuntimeError("CIRISVerify returned empty pubkey — key may not be initialized")

    actor_id_b64 = base64.b64encode(pubkey_bytes).decode("ascii")
    agent_id = os.environ.get("CIRIS_AGENT_ID")
    if agent_id:
        signing_key_id = f"agent-{agent_id}"
    else:
        fingerprint = hashlib.sha256(pubkey_bytes).hexdigest()[:12]
        signing_key_id = f"agent-{fingerprint}"
    return pubkey_bytes, actor_id_b64, signing_key_id


def sign_with_verifier(canonical_bytes: bytes) -> bytes:
    """Sign `canonical_bytes` with CIRISVerify's TPM-backed Ed25519 key.

    Caller supplies the bytes that persist's audit_canonicalize_for_signing
    returns. The same key is used for the bridge entry and every
    subsequent regular entry — single key, single chain.
    """
    from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
        get_verifier,
    )

    verifier = get_verifier()
    if verifier is None:
        raise RuntimeError("CIRISVerify verifier unavailable — cannot sign")
    sig: bytes = verifier.sign_ed25519_sync(canonical_bytes)
    return sig


def resolve_tenant_id() -> str:
    """Tenant ID for persist's cirislens_audit_log rows.

    Per AUDIT_CHAIN_BRIDGE.md §2.1: prefer CIRIS_AGENT_ID (stable per
    deployment); otherwise the literal string "agent-default" so
    operator-less single-agent installs still partition correctly.
    """
    agent_id: Optional[str] = os.environ.get("CIRIS_AGENT_ID")
    return agent_id if agent_id else "agent-default"


__all__ = ["get_signer_material", "sign_with_verifier", "resolve_tenant_id"]
