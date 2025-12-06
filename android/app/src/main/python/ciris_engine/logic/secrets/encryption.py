"""
Cryptographic functions for CIRIS secrets management.

Provides AES-256-GCM encryption with per-secret keys derived from a master key.
Implements secure key derivation, rotation, and forward secrecy.
"""

import logging
import secrets
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecretsEncryption:
    """Handles encryption/decryption of secrets using AES-256-GCM"""

    def __init__(self, master_key: Optional[bytes] = None) -> None:
        """
        Initialize with a master key. If not provided, generates a new one.

        Args:
            master_key: 32-byte master key for deriving per-secret keys
        """
        if master_key is None:
            self.master_key = self._generate_master_key()
            logger.warning("Generated new master key - ensure this is persisted securely")
        else:
            if len(master_key) != 32:
                raise ValueError("Master key must be exactly 32 bytes")
            self.master_key = master_key

    def _generate_master_key(self) -> bytes:
        """Generate a new 256-bit master key"""
        return secrets.token_bytes(32)

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive a per-secret key from master key + salt using PBKDF2

        Args:
            salt: 16-byte cryptographic salt

        Returns:
            32-byte derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(self.master_key)

    def encrypt_secret(self, value: str) -> Tuple[bytes, bytes, bytes]:
        """
        Encrypt a secret value using AES-256-GCM

        Args:
            value: The secret string to encrypt

        Returns:
            Tuple of (encrypted_value, salt, nonce)
        """
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)

        key = self._derive_key(salt)

        aesgcm = AESGCM(key)
        encrypted_value = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

        logger.debug(f"Encrypted secret of length {len(value)} characters")
        return encrypted_value, salt, nonce

    def decrypt_secret(self, encrypted_value: bytes, salt: bytes, nonce: bytes) -> str:
        """
        Decrypt a secret value using AES-256-GCM

        Args:
            encrypted_value: The encrypted secret data
            salt: The salt used for key derivation
            nonce: The nonce used for encryption

        Returns:
            The decrypted secret string

        Raises:
            InvalidSignature: If decryption fails (wrong key, corrupted data, etc.)
        """
        key = self._derive_key(salt)

        aesgcm = AESGCM(key)
        decrypted_bytes = aesgcm.decrypt(nonce, encrypted_value, None)

        logger.debug("Successfully decrypted secret")
        return decrypted_bytes.decode("utf-8")

    def rotate_master_key(self, new_master_key: Optional[bytes] = None) -> bytes:
        """
        Rotate the master key. This should be used with SecretsStore.reencrypt_all()

        Args:
            new_master_key: New master key, or None to generate one

        Returns:
            The new master key that was set
        """
        _old_key = self.master_key

        if new_master_key is None:
            self.master_key = self._generate_master_key()
        else:
            if len(new_master_key) != 32:
                raise ValueError("New master key must be exactly 32 bytes")
            self.master_key = new_master_key

        logger.info("Master key rotated successfully")
        return self.master_key

    def get_master_key(self) -> bytes:
        """Get the current master key (for backup/persistence)"""
        return self.master_key

    @staticmethod
    def generate_key_from_password(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Generate a master key from a password (for human-memorable keys)

        Args:
            password: The password to derive key from
            salt: Optional salt, generates new one if not provided

        Returns:
            Tuple of (key, salt)
        """
        if salt is None:
            salt = secrets.token_bytes(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )

        key = kdf.derive(password.encode("utf-8"))
        return key, salt

    def test_encryption(self) -> bool:
        """
        Test that encryption/decryption is working correctly

        Returns:
            True if test passes, False otherwise
        """
        try:
            test_secret = "test_secret_value_123"
            encrypted, salt, nonce = self.encrypt_secret(test_secret)
            decrypted = self.decrypt_secret(encrypted, salt, nonce)

            if decrypted == test_secret:
                logger.debug("Encryption test passed")
                return True
            else:
                logger.error("Encryption test failed: decrypted value doesn't match")
                return False

        except Exception as e:
            logger.error(f"Encryption test failed with exception: {e}")
            return False
