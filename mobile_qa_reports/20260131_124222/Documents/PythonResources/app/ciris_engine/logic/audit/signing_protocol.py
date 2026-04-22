"""
Algorithm-agnostic signing protocol for audit and trace signing.

Designed for migration path: RSA-2048 -> Ed25519 -> PQC (ML-DSA/SLH-DSA)

The protocol abstracts the signing algorithm so the system can:
1. Support multiple algorithms during migration periods
2. Verify historical signatures with old algorithms
3. Sign new entries with the current algorithm
4. Eventually migrate to post-quantum algorithms
"""

import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Error message constants
SIGNER_NOT_INITIALIZED = "Signer not initialized"


class SigningAlgorithm(str, Enum):
    """Supported signing algorithms with migration path to PQC."""

    # Legacy (deprecated, verification only)
    RSA_2048_PSS = "rsa_2048_pss"

    # Current default
    ED25519 = "ed25519"

    # Future PQC options (placeholder for when libraries mature)
    # ML_DSA_65 = "ml_dsa_65"  # NIST FIPS 204 (Dilithium)
    # SLH_DSA_128S = "slh_dsa_128s"  # NIST FIPS 205 (SPHINCS+)


@runtime_checkable
class SignerProtocol(Protocol):
    """Protocol for algorithm-agnostic signing operations.

    Implementations must provide:
    - algorithm: The signing algorithm used
    - key_id: Unique identifier for the key (hash of public key)
    - public_key_bytes: Raw public key bytes for registration
    - sign(): Sign data and return signature bytes
    - verify(): Verify a signature against data
    """

    @property
    def algorithm(self) -> SigningAlgorithm:
        """The signing algorithm used by this signer."""
        ...

    @property
    def key_id(self) -> str:
        """Unique identifier for this key (format: agent-{hash[:12]})."""
        ...

    @property
    def public_key_bytes(self) -> bytes:
        """Raw public key bytes (for registration with external services)."""
        ...

    @property
    def public_key_base64(self) -> str:
        """Base64-encoded public key (for API registration)."""
        ...

    def sign(self, data: bytes) -> bytes:
        """Sign data and return raw signature bytes."""
        ...

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature against data."""
        ...


class BaseSigner(ABC):
    """Base class for signing implementations."""

    _algorithm: SigningAlgorithm
    _key_id: Optional[str] = None
    _private_key: Any = None
    _public_key: Any = None

    @property
    def algorithm(self) -> SigningAlgorithm:
        return self._algorithm

    @property
    def key_id(self) -> str:
        if not self._key_id:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        return self._key_id

    @property
    @abstractmethod
    def public_key_bytes(self) -> bytes:
        """Raw public key bytes."""
        ...

    @property
    def public_key_base64(self) -> str:
        """Base64-encoded public key."""
        return base64.b64encode(self.public_key_bytes).decode()

    @abstractmethod
    def sign(self, data: bytes) -> bytes:
        """Sign data and return raw signature bytes."""
        ...

    @abstractmethod
    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature against data."""
        ...

    @abstractmethod
    def _generate_keypair(self) -> None:
        """Generate a new key pair."""
        ...

    @abstractmethod
    def _load_keypair(self, key_path: Path) -> bool:
        """Load key pair from file. Returns True if successful."""
        ...

    @abstractmethod
    def _save_keypair(self, key_path: Path) -> None:
        """Save key pair to file."""
        ...

    def _compute_key_id(self, public_key_bytes: bytes) -> str:
        """Compute key ID from public key bytes.

        Format: agent-{sha256(pubkey)[:12]}
        This matches the covenant metrics key_id format.
        """
        return f"agent-{hashlib.sha256(public_key_bytes).hexdigest()[:12]}"


class Ed25519Signer(BaseSigner):
    """Ed25519 signing implementation.

    Ed25519 advantages over RSA-2048:
    - Faster signing and verification
    - Smaller signatures (64 bytes vs 256 bytes)
    - Smaller keys (32 bytes vs 256 bytes)
    - Deterministic signatures (no random component)
    - Resistant to side-channel attacks
    - Simple and auditable implementation
    """

    def __init__(self) -> None:
        self._algorithm = SigningAlgorithm.ED25519
        self._private_key = None
        self._public_key = None
        self._key_id = None

    @property
    def public_key_bytes(self) -> bytes:
        if not self._public_key:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        from cryptography.hazmat.primitives import serialization

        result: bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return result

    def sign(self, data: bytes) -> bytes:
        if not self._private_key:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        result: bytes = self._private_key.sign(data)
        return result

    def verify(self, data: bytes, signature: bytes) -> bool:
        if not self._public_key:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        try:
            self._public_key.verify(signature, data)
            return True
        except Exception:
            return False

    def _generate_keypair(self) -> None:
        from cryptography.hazmat.primitives.asymmetric import ed25519

        self._private_key = ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._key_id = self._compute_key_id(self.public_key_bytes)
        logger.info(f"Generated new Ed25519 keypair (key_id={self._key_id})")

    def _load_keypair(self, key_path: Path) -> bool:
        """Load Ed25519 keypair from raw 32-byte private key file."""
        try:
            if not key_path.exists():
                return False

            from cryptography.hazmat.primitives.asymmetric import ed25519

            private_bytes = key_path.read_bytes()
            self._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
            self._public_key = self._private_key.public_key()
            self._key_id = self._compute_key_id(self.public_key_bytes)
            logger.info(f"Loaded Ed25519 keypair from {key_path} (key_id={self._key_id})")
            return True
        except Exception as e:
            logger.debug(f"Could not load Ed25519 key from {key_path}: {e}")
            return False

    def _save_keypair(self, key_path: Path) -> None:
        """Save Ed25519 keypair as raw 32-byte private key file."""
        if not self._private_key:
            raise RuntimeError("No keypair to save")

        import os

        from cryptography.hazmat.primitives import serialization

        # Ensure parent directory exists
        key_path.parent.mkdir(parents=True, exist_ok=True)

        # Get raw private key bytes (32 bytes)
        private_bytes = self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

        key_path.write_bytes(private_bytes)
        os.chmod(key_path, 0o600)  # Restrictive permissions
        logger.info(f"Saved Ed25519 keypair to {key_path}")


class UnifiedSigningKey:
    """Unified signing key management for audit and covenant metrics.

    Manages a single Ed25519 key used for:
    1. Audit trail signing
    2. Covenant metrics trace signing
    3. Future: any other cryptographic signing needs

    The key is stored at: data/agent_signing.key (32-byte raw Ed25519 private key)
    Key ID format: agent-{sha256(pubkey)[:12]}
    """

    # Standard key location
    DEFAULT_KEY_PATH = Path("data/agent_signing.key")
    DOCKER_KEY_PATH = Path("/app/data/agent_signing.key")

    def __init__(self, key_path: Optional[Path] = None) -> None:
        """Initialize unified signing key manager.

        Args:
            key_path: Custom key path (defaults to data/agent_signing.key)
        """
        self._key_path = key_path
        self._signer: Optional[Ed25519Signer] = None
        self._initialized = False

    @property
    def signer(self) -> Ed25519Signer:
        if not self._signer:
            raise RuntimeError("UnifiedSigningKey not initialized")
        return self._signer

    @property
    def key_id(self) -> str:
        return self.signer.key_id

    @property
    def public_key_bytes(self) -> bytes:
        return self.signer.public_key_bytes

    @property
    def public_key_base64(self) -> str:
        return self.signer.public_key_base64

    @property
    def algorithm(self) -> SigningAlgorithm:
        return self.signer.algorithm

    def initialize(self) -> None:
        """Initialize the signing key (load existing or generate new)."""
        if self._initialized:
            return

        self._signer = Ed25519Signer()

        # Try to load from configured or default locations
        key_locations = []
        if self._key_path:
            key_locations.append(self._key_path)
        key_locations.extend(
            [
                self.DEFAULT_KEY_PATH,
                self.DOCKER_KEY_PATH,
            ]
        )

        for key_path in key_locations:
            if self._signer._load_keypair(key_path):
                self._key_path = key_path
                self._initialized = True
                return

        # No existing key found - generate new one
        logger.info("No unified signing key found, generating new Ed25519 keypair...")
        self._signer._generate_keypair()

        # Save to first writable location
        for key_path in key_locations:
            try:
                self._signer._save_keypair(key_path)
                self._key_path = key_path
                break
            except Exception as e:
                logger.debug(f"Could not save key to {key_path}: {e}")

        self._initialized = True

    def sign(self, data: bytes) -> bytes:
        """Sign data and return signature bytes."""
        return self.signer.sign(data)

    def sign_base64(self, data: bytes) -> str:
        """Sign data and return URL-safe base64 signature."""
        sig_bytes = self.sign(data)
        return base64.urlsafe_b64encode(sig_bytes).decode().rstrip("=")

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature against data."""
        return self.signer.verify(data, signature)

    def verify_base64(self, data: bytes, signature_b64: str) -> bool:
        """Verify a URL-safe base64 signature against data."""
        # Restore padding
        padding_needed = 4 - (len(signature_b64) % 4)
        if padding_needed != 4:
            signature_b64 += "=" * padding_needed
        sig_bytes = base64.urlsafe_b64decode(signature_b64)
        return self.verify(data, sig_bytes)

    def get_registration_payload(self, description: str = "") -> Dict[str, Any]:
        """Get payload for registering public key with CIRISLens.

        Returns dict suitable for POST to /api/v1/covenant/public-keys
        """
        return {
            "key_id": self.key_id,
            "public_key_base64": self.public_key_base64,
            "algorithm": self.algorithm.value,
            "description": description,
        }


# Global singleton for unified signing key
_unified_key: Optional[UnifiedSigningKey] = None


def get_unified_signing_key() -> UnifiedSigningKey:
    """Get the global unified signing key instance.

    This ensures all components (audit, covenant metrics, etc.)
    use the same signing key.
    """
    global _unified_key
    if _unified_key is None:
        _unified_key = UnifiedSigningKey()
        _unified_key.initialize()
    return _unified_key


def reset_unified_signing_key() -> None:
    """Reset the global unified signing key (for testing)."""
    global _unified_key
    _unified_key = None
