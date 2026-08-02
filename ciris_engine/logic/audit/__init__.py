"""Audit subsystem for CIRIS Engine.

2.9.7 DRY purge (second-signer removal): the substrate owns the audit
chain AND the signing identity. All audit/trace signatures come from the
persist Engine's federation-registered local signer:

- ``engine.local_sign(data)``          — Ed25519 signature (64 raw bytes)
- ``engine.local_public_key_b64()``    — the signer's public key (base64)
- ``engine.local_derived_key_id()``    — the federation-registered key_id
  (``derive_key_id(<alias>, <pubkey>)``); the ONLY id the substrate
  verifies against. Stamping anything else lands ``verify_unknown_key``.

Removed in 2.9.7:
- signing_protocol.py (UnifiedSigningKey / CIRISVerifySigner): a SECOND
  Ed25519 signer identity (``agent-{sha12}`` via CIRISVerify) duplicating
  the persist keyring signer. Its keys were never federation-registered,
  so peer nodes rejected them with ``verify_unknown_key``.
- persist_signing.py: signer-material helpers for the removed identity.
- chain_bridge.py: one-shot 2.9.0 legacy-chain bridge (signed with the
  removed identity). Pre-2.9.0 installs must upgrade through 2.9.x first.

The only agent-layer concern left here is tenant partitioning for
persist's ``cirislens_audit_log`` / incident rows.
"""

import os

__all__ = ["resolve_tenant_id"]


def resolve_tenant_id() -> str:
    """Tenant ID for persist's cirislens_audit_log / incident rows.

    Prefer CIRIS_AGENT_ID (stable per deployment); otherwise the literal
    string "agent-default" so operator-less single-agent installs still
    partition correctly. Readers and writers MUST resolve the tenant via
    this one function or the audit trail appears empty on read.
    """
    agent_id = os.environ.get("CIRIS_AGENT_ID")
    return agent_id if agent_id else "agent-default"
