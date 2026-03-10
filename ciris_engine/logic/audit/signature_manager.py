"""
Signature manager for signed audit trail system.

Now uses Ed25519 via the unified signing key (shared with accord metrics).
Legacy RSA-2048 verification is maintained for backward compatibility.

Migration path:
- New installations use Ed25519 automatically
- Existing RSA installations can migrate via database_maintenance.migrate_audit_key_to_ed25519()
- RSA signatures can still be verified for historical entries
"""

import base64
import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class AuditSignatureManager:
    """Manages signing keys and signatures for audit entries.

    Now uses the unified Ed25519 signing key by default.
    RSA-2048 verification is maintained for backward compatibility with existing audit chains.
    """

    def __init__(self, db_path: str, time_service: TimeServiceProtocol) -> None:
        self.db_path = db_path
        self._time_service = time_service

        # Unified Ed25519 signing key (managed by CIRISVerify)
        self._unified_key: Optional[Any] = None
        self._key_id: Optional[str] = None
        self._using_ed25519 = False

        # Legacy RSA key (for verification only)
        self._legacy_rsa_public_key: Optional[PublicKeyTypes] = None

    def initialize(self) -> None:
        """Initialize the signature manager using unified Ed25519 key from CIRISVerify."""
        try:
            self._load_unified_key()
            self._register_public_key()
            logger.info(f"Signature manager initialized with Ed25519 key ID: {self._key_id}")
        except Exception as e:
            logger.error(f"Failed to initialize signature manager: {e}")
            raise

    def _load_unified_key(self) -> None:
        """Load the unified Ed25519 signing key from CIRISVerify."""
        from .signing_protocol import get_unified_signing_key

        self._unified_key = get_unified_signing_key()

        # Set callback for key lifecycle events (Portal import, ephemeral creation)
        self._unified_key.set_key_registration_callback(self._on_key_registered)

        # Get key_id if available (may be None if no key yet)
        if self._unified_key.has_key:
            self._key_id = self._unified_key.key_id
        self._using_ed25519 = True

    def _on_key_registered(self, key_id: str, public_key_base64: str, algorithm: str) -> None:
        """Callback when a new key is registered via Portal import or ephemeral creation."""
        logger.info(f"Key lifecycle event: registering {key_id} in audit_signing_keys")
        self._key_id = key_id

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if key already exists
            cursor.execute("SELECT key_id FROM audit_signing_keys WHERE key_id = ?", (key_id,))

            if cursor.fetchone():
                logger.debug(f"Key {key_id} already registered")
                conn.close()
                return

            # Insert new key
            cursor.execute(
                """
                INSERT INTO audit_signing_keys
                (key_id, public_key, algorithm, key_size, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    key_id,
                    public_key_base64,
                    algorithm,
                    256 if algorithm == "ed25519" else 2048,
                    self._time_service.now_iso(),
                ),
            )

            conn.commit()
            conn.close()

            logger.info(f"Registered key in audit_signing_keys: {key_id}")

        except sqlite3.Error as e:
            logger.error(f"Failed to register key {key_id}: {e}")

    def _register_public_key(self) -> None:
        """Register the Ed25519 public key in the database.

        Delegates to _on_key_registered for consistency across all key lifecycle ops.
        If no key exists yet (waiting for Portal import or ephemeral creation),
        registration is deferred - the callback will handle it when the key is created.
        """
        if not self._unified_key:
            raise RuntimeError("Unified key manager not initialized")

        # If no key exists yet, skip registration - callback will handle it
        if not self._key_id:
            logger.info("No signing key available yet - registration deferred to callback")
            return

        self._on_key_registered(
            key_id=self._key_id,
            public_key_base64=self._unified_key.public_key_base64,
            algorithm="ed25519",
        )

    def sign_entry(self, entry_hash: str) -> str:
        """Sign an entry hash and return base64 encoded signature."""
        if not self._unified_key:
            raise RuntimeError("Signature manager not initialized")

        try:
            # Sign using Ed25519 unified key
            signature_bytes = self._unified_key.sign(entry_hash.encode("utf-8"))
            return base64.b64encode(signature_bytes).decode("ascii")

        except Exception as e:
            logger.error(f"Failed to sign entry: {e}")
            raise

    def verify_signature(self, entry_hash: str, signature: str, key_id: Optional[str] = None) -> bool:
        """Verify a signature against an entry hash.

        Supports both Ed25519 (current) and RSA-2048 (legacy) signatures.
        """
        try:
            signature_bytes = base64.b64decode(signature.encode("ascii"))

            # If verifying with current key (Ed25519)
            if key_id is None or key_id == self._key_id:
                if self._unified_key:
                    result: bool = self._unified_key.verify(entry_hash.encode("utf-8"), signature_bytes)
                    return result

            # Try to load key info from database to determine algorithm
            key_info = self._load_key_info(key_id or self._key_id or "")
            if not key_info:
                logger.error(f"Key not found: {key_id}")
                return False

            algorithm = str(key_info.get("algorithm", ""))
            public_key_data = str(key_info.get("public_key", ""))

            # Ed25519 verification
            if algorithm == "ed25519":
                return self._verify_ed25519(entry_hash, signature_bytes, public_key_data)

            # RSA-PSS verification (legacy)
            elif algorithm in ("rsa-pss", "rsa_2048_pss"):
                return self._verify_rsa(entry_hash, signature_bytes, public_key_data)

            else:
                logger.error(f"Unknown algorithm: {algorithm}")
                return False

        except InvalidSignature:
            logger.warning(f"Invalid signature for entry hash: {entry_hash[:16]}...")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

    def _verify_ed25519(self, entry_hash: str, signature_bytes: bytes, public_key_b64: str) -> bool:
        """Verify an Ed25519 signature."""
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519

            # Decode base64 public key
            public_key_bytes = base64.b64decode(public_key_b64)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

            public_key.verify(signature_bytes, entry_hash.encode("utf-8"))
            return True
        except Exception as e:
            logger.debug(f"Ed25519 verification failed: {e}")
            return False

    def _verify_rsa(self, entry_hash: str, signature_bytes: bytes, public_key_pem: str) -> bool:
        """Verify an RSA-PSS signature (legacy)."""
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))

            if not isinstance(public_key, rsa.RSAPublicKey):
                logger.error("Expected RSA public key")
                return False

            public_key.verify(
                signature_bytes,
                entry_hash.encode("utf-8"),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )
            return True
        except Exception as e:
            logger.debug(f"RSA verification failed: {e}")
            return False

    def _load_key_info(self, key_id: str) -> Optional[JSONDict]:
        """Load key info from the database by key ID."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT public_key, algorithm FROM audit_signing_keys WHERE key_id = ?",
                (key_id,),
            )

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            return {"public_key": row[0], "algorithm": row[1]}

        except Exception as e:
            logger.error(f"Failed to load key info {key_id}: {e}")
            return None

    def rotate_keys(self) -> str:
        """Rotate signing keys is not supported with unified key management.

        Use database_maintenance.migrate_audit_key_to_ed25519() for migration.
        """
        logger.warning("Key rotation is deprecated - unified key is managed centrally")
        # Just return the current key ID
        return self._key_id or ""

    def _revoke_key(self, key_id: str) -> None:
        """Mark a key as revoked in the database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE audit_signing_keys
                SET revoked_at = ?
                WHERE key_id = ?
            """,
                (self._time_service.now_iso(), key_id),
            )

            conn.commit()
            conn.close()

            logger.info(f"Revoked signing key: {key_id}")

        except sqlite3.Error as e:
            logger.error(f"Failed to revoke key {key_id}: {e}")

    def get_key_info(self) -> JSONDict:
        """Get information about the current signing key.

        Returns:
            Dict containing key metadata (key_id, algorithm, key_size, etc.)
        """
        if not self._key_id:
            return {"error": "Not initialized"}

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT key_id, algorithm, key_size, created_at, revoked_at
                FROM audit_signing_keys
                WHERE key_id = ?
            """,
                (self._key_id,),
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    "key_id": row[0],
                    "algorithm": row[1],
                    "key_size": row[2],
                    "created_at": row[3],
                    "revoked_at": row[4],
                    "active": row[4] is None,
                    "using_unified_key": self._using_ed25519,
                }
            else:
                return {"error": "Key not found in database"}

        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}

    @property
    def key_id(self) -> Optional[str]:
        """Get the current key ID."""
        return self._key_id

    def test_signing(self) -> bool:
        """Test that signing and verification work correctly.

        Retries with backoff if attestation is in progress (sign_ed25519 blocked).
        """
        import time

        max_retries = 10
        base_delay = 0.5  # 500ms as suggested by ciris_verify

        for attempt in range(max_retries):
            try:
                test_data = "test_entry_hash_12345"
                signature = self.sign_entry(test_data)
                verified = self.verify_signature(test_data, signature)

                if verified:
                    if attempt > 0:
                        logger.info(f"Signature test passed after {attempt + 1} attempts (waited for attestation)")
                    else:
                        logger.debug("Signature test passed (Ed25519)")
                    return True
                else:
                    logger.error("Signature test failed - verification failed")
                    return False

            except Exception as e:
                error_msg = str(e)
                # Check if attestation is blocking signing - retry with backoff
                if "Attestation in progress" in error_msg or "sign_ed25519 blocked" in error_msg:
                    if attempt < max_retries - 1:
                        delay = base_delay * (1.5**attempt)  # Exponential backoff
                        logger.info(
                            f"[signing] Attestation in progress, waiting {delay:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(
                            f"Signature test failed - attestation still in progress after {max_retries} retries"
                        )
                        return False
                else:
                    logger.error(f"Signature test failed with exception: {e}")
                    return False

        return False
