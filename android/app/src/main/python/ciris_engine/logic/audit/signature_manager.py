"""
Signature manager for signed audit trail system.

Manages RSA keys and digital signatures for audit entry non-repudiation.
Designed for resource-constrained deployments with minimal overhead.
"""

import base64
import hashlib
import logging
import os
import sqlite3
from pathlib import Path
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.types import PrivateKeyTypes, PublicKeyTypes

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class AuditSignatureManager:
    """Manages signing keys and signatures for audit entries"""

    def __init__(self, key_path: str, db_path: str, time_service: TimeServiceProtocol) -> None:
        self.key_path = Path(key_path)
        self.db_path = db_path
        self._time_service = time_service
        self._private_key: Optional[PrivateKeyTypes] = None
        self._public_key: Optional[PublicKeyTypes] = None
        self._key_id: Optional[str] = None

        # Ensure key directory exists
        self.key_path.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        """Initialize the signature manager by loading or generating keys"""
        if self.key_path == Path("/") or not os.access(self.key_path, os.W_OK):
            raise PermissionError(f"Key path {self.key_path} is not writable")
        try:
            self._load_or_generate_keys()
            self._register_public_key()
            logger.info(f"Signature manager initialized with key ID: {self._key_id}")
        except Exception as e:
            logger.error(f"Failed to initialize signature manager: {e}")
            raise

    def _load_or_generate_keys(self) -> None:
        """Load existing keys or generate new ones"""
        private_key_path = self.key_path / "audit_signing_private.pem"
        public_key_path = self.key_path / "audit_signing_public.pem"

        try:
            # Try to load existing keys
            if private_key_path.exists() and public_key_path.exists():
                logger.info("Loading existing audit signing keys")

                with open(private_key_path, "rb") as f:
                    self._private_key = serialization.load_pem_private_key(f.read(), password=None)

                with open(public_key_path, "rb") as f:
                    self._public_key = serialization.load_pem_public_key(f.read())

            else:
                # Generate new key pair
                logger.info("Generating new audit signing keys")
                self._generate_new_keypair()

        except Exception as e:
            logger.warning(f"Failed to load keys, generating new ones: {e}")
            self._generate_new_keypair()

        # Compute key ID from public key
        self._key_id = self._compute_key_id()

    def _generate_new_keypair(self) -> None:
        """Generate a new RSA key pair"""
        self._private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        self._public_key = self._private_key.public_key()

        self._save_keys()

    def _save_keys(self) -> None:
        """Save the key pair to disk"""
        if not self._private_key or not self._public_key:
            raise RuntimeError("Keys not initialized")

        private_key_path = self.key_path / "audit_signing_private.pem"
        public_key_path = self.key_path / "audit_signing_public.pem"

        # Save private key
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        with open(private_key_path, "wb") as f:
            f.write(private_pem)

        # Set restrictive permissions on private key
        os.chmod(private_key_path, 0o600)

        # Save public key
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        with open(public_key_path, "wb") as f:
            f.write(public_pem)

        logger.info("Audit signing keys saved to disk")

    def _compute_key_id(self) -> str:
        """Compute a unique identifier for the public key"""
        if not self._public_key:
            raise RuntimeError("Public key not initialized")

        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        hash_bytes = hashlib.sha256(public_pem).digest()
        return base64.b64encode(hash_bytes[:16]).decode("ascii")

    def _register_public_key(self) -> None:
        """Register the public key in the database"""
        if not self._public_key or not self._key_id:
            raise RuntimeError("Keys not initialized for registration")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Check if key already exists
            cursor.execute("SELECT key_id FROM audit_signing_keys WHERE key_id = ?", (self._key_id,))

            if cursor.fetchone():
                logger.debug(f"Key {self._key_id} already registered")
                conn.close()
                return

            # Insert new key
            public_pem = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode("ascii")

            cursor.execute(
                """
                INSERT INTO audit_signing_keys
                (key_id, public_key, algorithm, key_size, created_at)
                VALUES (?, ?, ?, ?, ?)
            """,
                (self._key_id, public_pem, "rsa-pss", 2048, self._time_service.now_iso()),
            )

            conn.commit()
            conn.close()

            logger.info(f"Registered public key in database: {self._key_id}")

        except sqlite3.Error as e:
            logger.error(f"Failed to register public key: {e}")

    def sign_entry(self, entry_hash: str) -> str:
        """Sign an entry hash and return base64 encoded signature"""
        if not self._private_key:
            raise RuntimeError("Signature manager not initialized")

        # Ensure we have an RSA key for signing
        if not isinstance(self._private_key, rsa.RSAPrivateKey):
            raise RuntimeError("Only RSA keys are supported for signing")

        try:
            # Sign the hash using RSA-PSS
            signature = self._private_key.sign(
                entry_hash.encode("utf-8"),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )

            # Return base64 encoded signature
            return base64.b64encode(signature).decode("ascii")

        except Exception as e:
            logger.error(f"Failed to sign entry: {e}")
            raise

    def verify_signature(self, entry_hash: str, signature: str, key_id: Optional[str] = None) -> bool:
        """Verify a signature against an entry hash"""
        try:
            if key_id is None or key_id == self._key_id:
                public_key = self._public_key
            else:
                public_key = self._load_public_key(key_id)
                if not public_key:
                    logger.error(f"Public key not found: {key_id}")
                    return False

            if not public_key:
                logger.error("No public key available for verification")
                return False

            if not isinstance(public_key, rsa.RSAPublicKey):
                logger.error("Only RSA keys are supported for verification")
                return False

            signature_bytes = base64.b64decode(signature.encode("ascii"))

            public_key.verify(
                signature_bytes,
                entry_hash.encode("utf-8"),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )

            return True

        except InvalidSignature:
            logger.warning(f"Invalid signature for entry hash: {entry_hash[:16]}...")
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

    def _load_public_key(self, key_id: str) -> Optional[PublicKeyTypes]:
        """Load a public key from the database by key ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT public_key FROM audit_signing_keys WHERE key_id = ?", (key_id,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return None

            # Load public key from PEM
            return serialization.load_pem_public_key(row[0].encode("ascii"))

        except Exception as e:
            logger.error(f"Failed to load public key {key_id}: {e}")
            return None

    def rotate_keys(self) -> str:
        """Rotate to a new key pair and return the new key ID"""
        logger.info("Rotating audit signing keys")

        if self._key_id:
            self._revoke_key(self._key_id)

        self._generate_new_keypair()
        self._key_id = self._compute_key_id()

        self._register_public_key()

        logger.info(f"Key rotation complete, new key ID: {self._key_id}")
        return self._key_id

    def _revoke_key(self, key_id: str) -> None:
        """Mark a key as revoked in the database"""
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
                }
            else:
                return {"error": "Key not found in database"}

        except sqlite3.Error as e:
            return {"error": f"Database error: {e}"}

    @property
    def key_id(self) -> Optional[str]:
        """Get the current key ID"""
        return self._key_id

    def test_signing(self) -> bool:
        """Test that signing and verification work correctly"""
        try:
            test_data = "test_entry_hash_12345"
            signature = self.sign_entry(test_data)
            verified = self.verify_signature(test_data, signature)

            if verified:
                logger.debug("Signature test passed")
                return True
            else:
                logger.error("Signature test failed - verification failed")
                return False

        except Exception as e:
            logger.error(f"Signature test failed with exception: {e}")
            return False
