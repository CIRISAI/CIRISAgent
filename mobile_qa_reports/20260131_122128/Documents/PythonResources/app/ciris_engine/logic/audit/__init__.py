"""Audit subsystem for CIRIS Engine.

Provides cryptographic hash chain and digital signature capabilities for audit trails.

Key components:
- AuditHashChain: Maintains hash chain integrity
- AuditSignatureManager: Now uses Ed25519 via unified signing key (shared with covenant metrics)
- AuditVerifier: Verifies signatures (supports both RSA and Ed25519)
- UnifiedSigningKey: Ed25519 signing key management (recommended)
- AuditKeyMigration: Migrate existing RSA audit chains to Ed25519

Note: New installations automatically use Ed25519. RSA-2048 is deprecated but
verification is maintained for backward compatibility with existing audit chains.
Use database_maintenance.migrate_audit_key_to_ed25519() to migrate existing chains.
"""

from .hash_chain import AuditHashChain
from .key_migration import AuditKeyMigration, MigrationResult, migrate_audit_key_to_ed25519
from .signature_manager import AuditSignatureManager
from .signing_protocol import (
    Ed25519Signer,
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
    # New unified signing
    "SigningAlgorithm",
    "SignerProtocol",
    "Ed25519Signer",
    "UnifiedSigningKey",
    "get_unified_signing_key",
    "reset_unified_signing_key",
    # Migration
    "AuditKeyMigration",
    "MigrationResult",
    "migrate_audit_key_to_ed25519",
]
