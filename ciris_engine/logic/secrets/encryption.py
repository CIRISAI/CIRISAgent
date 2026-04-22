"""
Cryptographic functions for CIRIS secrets management.

Provides AES-256-GCM encryption with per-secret keys derived from a master key.
Implements secure key derivation, rotation, and forward secrecy.

Supports both software (file-based) and hardware-backed (CIRISVerify) key storage:
- Software mode: Master key stored in file, derived using PBKDF2
- Hardware mode: Master key in CIRISVerify TPM/Keystore with multiple derivation strategies:
  - Native encryption (v1.6.0+): Direct hardware AES-GCM encryption/decryption
  - Symmetric derivation (v1.6.0+): HKDF-based key derivation
  - Signing derivation (v1.5.0+): Ed25519 signature-based key derivation
"""

import logging
import secrets
from typing import TYPE_CHECKING, Dict, Literal, Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

if TYPE_CHECKING:
    from ciris_adapters.ciris_verify.ffi_bindings.client import CIRISVerify

logger = logging.getLogger(__name__)

KeyStorageMode = Literal["software", "hardware", "auto"]


class SecretsEncryption:
    """Handles encryption/decryption of secrets using AES-256-GCM

    Supports both software and hardware-backed key storage modes:
    - Software: Master key in memory/file, PBKDF2 key derivation
    - Hardware: Master key in CIRISVerify TPM/Keystore with multiple strategies:
      - Native encryption (v1.6.0+): Hardware AES-GCM encryption/decryption
      - Symmetric derivation (v1.6.0+): HKDF-based key derivation
      - Signing derivation (v1.5.0+): Ed25519 signature-based derivation
    """

    def __init__(self, master_key: Optional[bytes] = None, key_storage_mode: KeyStorageMode = "auto") -> None:
        """
        Initialize with a master key. If not provided, generates a new one.

        Args:
            master_key: 32-byte master key for deriving per-secret keys (software mode only)
            key_storage_mode: Storage mode - 'software', 'hardware', or 'auto'
        """
        self.key_storage_mode: KeyStorageMode = key_storage_mode
        self._hardware_key_id = "secrets:master_v1"
        self._hardware_available = False
        self._verifier: Optional["CIRISVerify"] = None

        # Try to initialize hardware backend if requested
        if key_storage_mode in ("hardware", "auto"):
            self._hardware_available = self._init_hardware_backend()

        # If hardware requested but not available, fall back to software
        if key_storage_mode == "hardware" and not self._hardware_available:
            logger.warning("Hardware key storage requested but not available - using software fallback")
            self.key_storage_mode = "software"
        elif key_storage_mode == "auto" and self._hardware_available:
            logger.info("Hardware key storage available - using CIRISVerify")
            self.key_storage_mode = "hardware"
        elif key_storage_mode == "auto" and not self._hardware_available:
            logger.debug("Hardware key storage not available - using software mode")
            self.key_storage_mode = "software"

        # Software mode: store master key in memory
        if self.key_storage_mode == "software":
            if master_key is None:
                self.master_key = self._generate_master_key()
                logger.warning("Generated new master key - ensure this is persisted securely")
            else:
                if len(master_key) != 32:
                    raise ValueError("Master key must be exactly 32 bytes")
                self.master_key = master_key
        else:
            # Hardware mode: master key stays in hardware, never in memory
            # Set to None to prevent accidental usage - get_master_key() will raise
            self.master_key = b""  # Placeholder - callers must not access this in hardware mode

        # Log encryption capabilities at startup
        capabilities = self.get_hardware_capabilities()
        mode_desc = "software-only" if self.key_storage_mode == "software" else "hardware-backed"
        logger.info(f"[SECRETS] Encryption mode: {mode_desc}, capabilities: {capabilities}")

    def _generate_master_key(self) -> bytes:
        """Generate a new 256-bit master key"""
        return secrets.token_bytes(32)

    def _init_hardware_backend(self) -> bool:
        """Initialize hardware key backend (CIRISVerify).

        Returns:
            True if hardware backend is available and initialized
        """
        try:
            # Import may not exist in CI or may be untyped - ignore all import errors
            from ciris_adapters.ciris_verify.verifier_singleton import get_verifier, has_verifier  # type: ignore

            if not has_verifier():
                return False

            self._verifier = get_verifier()
            return True
        except ImportError:
            logger.debug("CIRISVerify adapter not available")
            return False
        except Exception as e:
            logger.debug(f"Failed to initialize hardware backend: {e}")
            return False

    def get_hardware_capabilities(self) -> Dict[str, bool]:
        """Get hardware encryption capabilities.

        Returns:
            Dict with capability flags:
            - hardware_available: bool - Any hardware support
            - native_encryption: bool - Direct encrypt/decrypt (v1.6.0+)
            - symmetric_derivation: bool - HKDF key derivation (v1.6.0+)
            - signing_derivation: bool - Sign-based key derivation (v1.5.0+)
            - software_only: bool - No hardware, software fallback
        """
        if not self._hardware_available or self._verifier is None:
            return {
                "hardware_available": False,
                "native_encryption": False,
                "symmetric_derivation": False,
                "signing_derivation": False,
                "software_only": True,
            }

        # Check for native encryption support (v1.6.0+)
        has_native_encryption = False
        has_symmetric_derivation = False
        try:
            # Native encryption methods are dynamically available in native library
            has_native_encryption = self._verifier.has_encryption_support()  # type: ignore[attr-defined]
            # If native encryption is available, symmetric derivation is also available
            has_symmetric_derivation = has_native_encryption
        except Exception:
            pass

        return {
            "hardware_available": True,
            "native_encryption": has_native_encryption,
            "symmetric_derivation": has_symmetric_derivation,
            "signing_derivation": True,  # Always true if hardware is available
            "software_only": False,
        }

    def get_encryption_key_ref(self) -> str:
        """Get the encryption key reference for secrets encrypted with current configuration.

        Returns:
            Key reference string:
            - "hardware_v1" - Native hardware AES-GCM encryption (v1.6.0+)
            - "master_key_v1" - Software encryption (or hardware with signing derivation)
        """
        if self.key_storage_mode == "hardware" and self._hardware_available:
            if self._verifier is not None:
                try:
                    if self._verifier.has_encryption_support():  # type: ignore[attr-defined]
                        return "hardware_v1"
                except (AttributeError, NotImplementedError):
                    pass
        return "master_key_v1"

    def _get_key_from_hardware(self, salt: bytes) -> bytes:
        """Derive encryption key from hardware-backed master key.

        Tries multiple derivation methods in order of preference:
        1. derive_symmetric_key (v1.6.0+) - HKDF-based, cleanest approach
        2. sign_with_named_key + hash - Ed25519 signature-based (v1.5.0+)

        Args:
            salt: 16-byte cryptographic salt

        Returns:
            32-byte derived encryption key
        """
        if not self._hardware_available or self._verifier is None:
            raise RuntimeError("Hardware backend not available")

        try:
            # Try native symmetric key derivation first (v1.6.0+)
            # This is the cleanest approach using HKDF
            try:
                # Native encryption methods are dynamically available
                derived_key: bytes = self._verifier.derive_symmetric_key(  # type: ignore[attr-defined]
                    self._hardware_key_id, context=b"ciris-secrets-v1:" + salt, key_length=32
                )
                return derived_key
            except (AttributeError, NotImplementedError):
                # Fall back to signing-based derivation
                pass

            # Fall back to signing-based derivation (v1.5.0+)
            # Sign the salt to get a deterministic 64-byte Ed25519 signature
            signature: bytes = self._verifier.sign_with_named_key(self._hardware_key_id, salt)

            # Use first 32 bytes as the derived key
            # This is deterministic and unique per salt
            return signature[:32]
        except Exception as e:
            logger.error(f"Hardware key derivation failed: {e}")
            raise RuntimeError(f"Hardware key derivation failed: {e}") from e

    def has_hardware_key(self) -> bool:
        """Check if hardware-backed master key exists.

        Returns:
            True if hardware key is stored in CIRISVerify
        """
        if not self._hardware_available or self._verifier is None:
            return False

        try:
            result: bool = self._verifier.has_named_key(self._hardware_key_id)
            return result
        except Exception:
            return False

    def store_key_in_hardware(self, master_key: bytes) -> bool:
        """Store master key in hardware-backed storage.

        Args:
            master_key: 32-byte master key to store

        Returns:
            True if successfully stored
        """
        if not self._hardware_available or self._verifier is None:
            logger.warning("Hardware backend not available for key storage")
            return False

        try:
            if len(master_key) != 32:
                raise ValueError("Master key must be exactly 32 bytes")

            result: bool = self._verifier.store_named_key(self._hardware_key_id, master_key)
            return result
        except Exception as e:
            logger.error(f"Failed to store key in hardware: {e}")
            return False

    def _derive_key(self, salt: bytes) -> bytes:
        """
        Derive a per-secret key from master key + salt.

        Uses hardware-backed signing if available, otherwise PBKDF2.

        Args:
            salt: 16-byte cryptographic salt

        Returns:
            32-byte derived key
        """
        # Hardware mode: use signing-based derivation
        if self.key_storage_mode == "hardware" and self._hardware_available:
            return self._get_key_from_hardware(salt)

        # Software mode: use PBKDF2
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

        Uses native hardware encryption when available (v1.6.0+),
        otherwise falls back to software AES-GCM with derived keys.

        Args:
            value: The secret string to encrypt

        Returns:
            Tuple of (encrypted_value, salt, nonce)
        """
        salt = secrets.token_bytes(16)

        # Try native hardware encryption first (v1.6.0+)
        if self.key_storage_mode == "hardware" and self._hardware_available and self._verifier is not None:
            try:
                # Check if native encryption is available (dynamically defined)
                if self._verifier.has_encryption_support():  # type: ignore[attr-defined]
                    # encrypt_with_named_key returns: nonce (12 bytes) || ciphertext || tag (16 bytes)
                    ciphertext_with_nonce: bytes = self._verifier.encrypt_with_named_key(  # type: ignore[attr-defined]
                        self._hardware_key_id,
                        value.encode("utf-8"),
                        aad=salt,  # Use salt as AAD for additional security
                    )
                    # Extract the nonce (first 12 bytes)
                    nonce = ciphertext_with_nonce[:12]
                    # The rest is the actual ciphertext (including the tag)
                    encrypted_value = ciphertext_with_nonce[12:]
                    logger.debug(f"Encrypted secret of length {len(value)} characters using native hardware encryption")
                    return encrypted_value, salt, nonce
            except (AttributeError, NotImplementedError):
                # Fall through to software encryption with derived key
                pass

        # Fall back to software AES-GCM with derived key
        nonce = secrets.token_bytes(12)
        key = self._derive_key(salt)

        aesgcm = AESGCM(key)
        encrypted_value = aesgcm.encrypt(nonce, value.encode("utf-8"), None)

        logger.debug(f"Encrypted secret of length {len(value)} characters")
        return encrypted_value, salt, nonce

    def decrypt_secret(
        self,
        encrypted_value: bytes,
        salt: bytes,
        nonce: bytes,
        encryption_key_ref: Optional[str] = None,
    ) -> str:
        """
        Decrypt a secret value using AES-256-GCM

        Uses native hardware decryption when available (v1.6.0+),
        otherwise falls back to software AES-GCM with derived keys.

        Args:
            encrypted_value: The encrypted secret data
            salt: The salt used for key derivation
            nonce: The nonce used for encryption
            encryption_key_ref: Optional key reference to validate compatibility.
                               If "hardware_v1" but v1.6.0 native encryption is unavailable,
                               raises an error instead of silently failing.

        Returns:
            The decrypted secret string

        Raises:
            InvalidSignature: If decryption fails (wrong key, corrupted data, etc.)
            RuntimeError: If encryption_key_ref indicates v1.6.0 native encryption
                         but the current CIRISVerify binary doesn't support it.
        """
        # Check for encryption method mismatch (v1.6.0 secret on v1.5.x binary)
        has_native_encryption = False
        if self._hardware_available and self._verifier is not None:
            try:
                # Native encryption methods are dynamically defined
                has_native_encryption = self._verifier.has_encryption_support()  # type: ignore[attr-defined]
            except (AttributeError, NotImplementedError):
                has_native_encryption = False

        if encryption_key_ref == "hardware_v1" and not has_native_encryption:
            # Secret was encrypted with v1.6.0 native encryption but we don't have it
            raise RuntimeError(
                f"Secret was encrypted with CIRISVerify v1.6.0+ native encryption "
                f"(encryption_key_ref={encryption_key_ref}) but current binary does not "
                f"support native encryption. Upgrade CIRISVerify to v1.6.0 or later."
            )

        # Try native hardware decryption first (v1.6.0+)
        if self.key_storage_mode == "hardware" and self._hardware_available and self._verifier is not None:
            try:
                # Check if native encryption is available
                if has_native_encryption:
                    # Reconstruct the ciphertext format: nonce || ciphertext || tag
                    ciphertext_with_nonce = nonce + encrypted_value
                    # Native encryption methods are dynamically defined
                    decrypted_bytes: bytes = self._verifier.decrypt_with_named_key(  # type: ignore[attr-defined]
                        self._hardware_key_id,
                        ciphertext_with_nonce,
                        aad=salt,  # Must match the AAD used during encryption
                    )
                    logger.debug("Successfully decrypted secret using native hardware decryption")
                    return decrypted_bytes.decode("utf-8")
            except (AttributeError, NotImplementedError):
                # Fall through to software decryption with derived key
                pass

        # Fall back to software AES-GCM with derived key
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
        """Get the current master key (for backup/persistence).

        Raises:
            RuntimeError: If in hardware mode (master key never leaves hardware)
        """
        if self.key_storage_mode == "hardware":
            raise RuntimeError(
                "Cannot retrieve master key in hardware mode - key is stored in secure hardware and never exposed"
            )
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
