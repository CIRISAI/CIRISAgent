"""Audit subsystem for CIRIS Engine.

Provides cryptographic hash chain and digital signature capabilities for audit trails.

Key components:
- AuditHashChain: Maintains hash chain integrity
- AuditSignatureManager: Uses CIRISVerify for all signing (via unified signing key)
- AuditVerifier: Verifies signatures (supports RSA legacy and Ed25519)
- UnifiedSigningKey: Ed25519 signing key management via CIRISVerify
- AuditKeyMigration: Migrate existing RSA audit chains to Ed25519

Note: CIRISVerify is the ONLY source of signing keys. It handles hardware-backed
storage (TPM, Keystore, Keychain) with software fallback. RSA-2048 verification
is maintained for backward compatibility with existing audit chains.
"""

from .hash_chain import AuditHashChain
from .key_migration import AuditKeyMigration, MigrationResult, migrate_audit_key_to_ed25519
from .signature_manager import AuditSignatureManager
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
    "AuditHashChain",
    "AuditSignatureManager",
    "AuditVerifier",
    # Unified signing via CIRISVerify
    "SigningAlgorithm",
    "SignerProtocol",
    "CIRISVerifySigner",
    "UnifiedSigningKey",
    "get_unified_signing_key",
    "reset_unified_signing_key",
    # Migration
    "AuditKeyMigration",
    "MigrationResult",
    "migrate_audit_key_to_ed25519",
]
