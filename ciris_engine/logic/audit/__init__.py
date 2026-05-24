"""Audit subsystem for CIRIS Engine.

Post-2.9.0 Phase 3a (CIRISAgent#763): the audit chain is owned by
persist's `cirislens_audit_log` substrate. The agent supplies the signing
material (via CIRISVerify) and reads/writes through persist.

Key components remaining at the agent layer:
- AuditVerifier: thin wrapper around `engine.audit_verify_chain`. Walks
  the chain end-to-end and reports outcome + tampered-sequence.
- UnifiedSigningKey + CIRISVerifySigner: Ed25519 signing key management
  via CIRISVerify (hardware-backed with software fallback).
- persist_signing helpers: actor_id / tenant_id / signing_key_id resolution
  for the persist-routed write path.

Removed in 2.9.0:
- AuditHashChain: persist owns the chain state + integrity.
- AuditSignatureManager: persist owns signing-key registration + verification.
- AuditKeyMigration: one-shot RSA→Ed25519 migration tooling; if it needs
  to run again, ship as `tools/ops/audit_key_migration.py`.
"""

from .signing_protocol import (
    CIRISVerifySigner,
    SignerProtocol,
    SigningAlgorithm,
    UnifiedSigningKey,
    get_unified_signing_key,
    reset_unified_signing_key,
)
from .verifier import AuditVerifier

__all__ = [
    "AuditVerifier",
    # Unified signing via CIRISVerify
    "SigningAlgorithm",
    "SignerProtocol",
    "CIRISVerifySigner",
    "UnifiedSigningKey",
    "get_unified_signing_key",
    "reset_unified_signing_key",
]
