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
from typing import Any, Dict, Optional, Protocol, cast, runtime_checkable

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
        This matches the accord metrics key_id format.
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


class CIRISVerifySigner(BaseSigner):
    """Signing implementation that delegates to CIRISVerify hardware vault.

    When the ciris-verify package is installed and the binary is available,
    this signer delegates all signing operations to the hardware security
    module via FFI. The private key never leaves the secure hardware.

    This integrates CIRISVerify as a "path" in the unified signing protocol:
    - If CIRISVerify binary is available → use hardware-bound key
    - If not → fall back to software Ed25519

    The algorithm depends on the hardware platform:
    - Mobile HSMs: ECDSA P-256
    - TPM/SGX: ECDSA P-256 or Ed25519
    - Software fallback: Ed25519
    """

    def __init__(self) -> None:
        self._algorithm = SigningAlgorithm.ED25519  # Updated after init
        self._key_id: Optional[str] = None
        self._client: Any = None  # CIRISVerify client, typed as Any to avoid import
        self._public_key_cache: Optional[bytes] = None
        self._algo_name: Optional[str] = None

    @property
    def public_key_bytes(self) -> bytes:
        if self._public_key_cache is None:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        return self._public_key_cache

    def sign(self, data: bytes) -> bytes:
        """Sign data via CIRISVerify FFI (direct sync call, no asyncio)."""
        if not self._client:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        try:
            return cast(bytes, self._client.sign_sync(data))
        except Exception as e:
            raise RuntimeError(f"CIRISVerify signing failed: {e}") from e

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify signature using the cached public key."""
        if self._algo_name and "Ed25519" in self._algo_name:
            try:
                from cryptography.hazmat.primitives.asymmetric import ed25519

                pub = ed25519.Ed25519PublicKey.from_public_bytes(self.public_key_bytes)
                pub.verify(signature, data)
                return True
            except Exception:
                return False
        elif self._algo_name and "P256" in self._algo_name:
            try:
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import ec, utils

                ec_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), self.public_key_bytes)
                # ECDSA P-256 signature is r||s (32+32 bytes)
                r = int.from_bytes(signature[:32], "big")
                s = int.from_bytes(signature[32:], "big")
                der_sig = utils.encode_dss_signature(r, s)
                ec_pub.verify(der_sig, data, ec.ECDSA(hashes.SHA256()))
                return True
            except Exception:
                return False
        return False

    def _generate_keypair(self) -> None:
        """Not applicable — key is managed by hardware."""
        raise RuntimeError("CIRISVerify manages keys in hardware — cannot generate locally")

    def _load_keypair(self, key_path: Path) -> bool:
        """Load CIRISVerify client and fetch public key.

        Runs initialization on a dedicated 8MB-stack thread because the Rust
        ciris_verify_init → LicenseEngine::with_config → Tokio runtime needs
        far more stack than the 544K iOS CIRISRuntime thread provides.
        After init, the client handle is safe for lightweight sign_sync() calls.

        Also handles auto-migration: if a file-based key exists but ciris_verify
        doesn't have one, imports it and deletes the file.
        """
        import threading

        # [client, key_bytes, algo, error, has_key]
        result: list[Any] = [None, None, None, None, False]

        def _init_on_large_stack() -> None:
            try:
                from ciris_verify import CIRISVerify

                client = CIRISVerify(skip_integrity_check=True)
                # Check if key already exists in secure storage
                has_key = client.has_key_sync()  # type: ignore[attr-defined, unused-ignore]
                result[4] = has_key

                if has_key:
                    # Key exists, get the public key
                    key_bytes, algo = client.get_public_key_sync()  # type: ignore[attr-defined, unused-ignore]
                    result[0] = client
                    result[1] = key_bytes
                    result[2] = algo
                else:
                    # No key yet - client is ready for import
                    result[0] = client
            except Exception as e:
                result[3] = e

        # Spawn a helper thread with 8MB stack for the heavy Rust/Tokio init.
        old_stack_size = threading.stack_size()
        try:
            threading.stack_size(8 * 1024 * 1024)  # 8MB
            t = threading.Thread(target=_init_on_large_stack, daemon=True)
            t.start()
            t.join(timeout=15)
        finally:
            threading.stack_size(old_stack_size)

        if result[3] is not None:
            logger.debug(f"CIRISVerify not available: {result[3]}")
            return False
        if result[0] is None:
            logger.debug("CIRISVerify initialization timed out")
            return False

        self._client = result[0]

        # If key exists in secure storage, use it
        if result[4] and result[1] is not None:
            self._public_key_cache = result[1]
            self._algo_name = result[2]
            self._key_id = self._compute_key_id(result[1])
            if self._algo_name and "Ed25519" in self._algo_name:
                self._algorithm = SigningAlgorithm.ED25519
            logger.info(f"CIRISVerify vault signer loaded (algo={self._algo_name}, key_id={self._key_id})")
            return True

        # No key in secure storage - try auto-migration from file
        return self._try_auto_migrate()

    def _try_auto_migrate(self) -> bool:
        """Try to auto-migrate an existing file-based key into ciris_verify.

        Checks standard key locations for existing Ed25519 keys,
        imports them into ciris_verify, validates, and deletes the original.
        """
        if not self._client:
            return False

        # Standard key locations to check
        key_locations = [
            Path("data/agent_signing.key"),
            Path("/app/data/agent_signing.key"),
        ]

        # Also check path resolution
        try:
            from ciris_engine.logic.utils.path_resolution import get_data_dir

            key_locations.insert(0, get_data_dir() / "agent_signing.key")
        except Exception:
            pass

        for key_path in key_locations:
            if not key_path.exists():
                continue

            try:
                key_bytes = key_path.read_bytes()
                if len(key_bytes) != 32:
                    logger.warning(f"Invalid key size at {key_path}: {len(key_bytes)} bytes")
                    continue

                # Import into ciris_verify
                logger.info(f"Auto-migrating key from {key_path} to ciris_verify secure storage")
                self._client.import_key_sync(key_bytes)

                # Fetch public key to validate
                pub_key, algo = self._client.get_ed25519_public_key_sync()
                self._public_key_cache = pub_key
                self._algo_name = algo
                self._key_id = self._compute_key_id(pub_key)

                if self._algo_name and "Ed25519" in self._algo_name:
                    self._algorithm = SigningAlgorithm.ED25519

                # Delete the original file after successful import
                try:
                    key_path.unlink()
                    logger.info(f"Deleted original key file after migration: {key_path}")
                except OSError as e:
                    logger.warning(f"Could not delete original key file {key_path}: {e}")

                logger.info(f"Key auto-migrated to ciris_verify (key_id={self._key_id})")
                return True

            except Exception as e:
                logger.warning(f"Failed to auto-migrate key from {key_path}: {e}")
                continue

        # No key to migrate - ciris_verify is ready but has no key
        logger.debug("CIRISVerify initialized but no key available (waiting for import)")
        return False

    def _save_keypair(self, key_path: Path) -> None:
        """Not applicable — key lives in hardware."""
        pass


class UnifiedSigningKey:
    """Unified signing key management for audit and accord metrics.

    Manages a single Ed25519 key used for:
    1. Audit trail signing
    2. Accord metrics trace signing
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
        self._signer: Optional[BaseSigner] = None
        self._initialized = False

    @property
    def signer(self) -> BaseSigner:
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
        """Initialize the signing key.

        Tries paths in order:
        1. CIRISVerify hardware vault (if ciris-verify package available)
        2. Existing Ed25519 key file
        3. Generate new Ed25519 key
        """
        if self._initialized:
            return

        # Path 1: Try CIRISVerify hardware vault
        if not self._key_path:  # Only if no explicit key path was given
            try:
                verify_signer = CIRISVerifySigner()
                if verify_signer._load_keypair(Path("__ciris_verify__")):
                    self._signer = verify_signer
                    self._initialized = True
                    logger.info(f"Using CIRISVerify hardware vault for signing " f"(key_id={verify_signer.key_id})")
                    return
            except Exception as e:
                logger.debug(f"CIRISVerify vault not available: {e}")

        # Path 2: Try existing Ed25519 key file
        self._signer = Ed25519Signer()

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

        # Path 3: No existing key found - generate new one
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

    def load_provisioned_key(self, ed25519_private_key_b64: str, save_path: Optional[Path] = None) -> None:
        """Load signing key for a Registry-provisioned agent.

        Tries CIRISVerify hardware/software vault first (sync FFI — no asyncio
        overhead). When CIRISVerify is available, it manages the signing key
        via Secure Enclave or software vault. The Registry-provisioned key is
        saved to disk as fallback only.

        Args:
            ed25519_private_key_b64: Base64-encoded 32-byte Ed25519 private key
            save_path: Where to save the fallback key (uses get_data_dir() if None)
        """
        import base64

        # Always save the provisioned key as fallback (uses writable path)
        from cryptography.hazmat.primitives.asymmetric import ed25519

        private_bytes = base64.b64decode(ed25519_private_key_b64)
        if len(private_bytes) != 32:
            raise ValueError(f"Expected 32-byte Ed25519 private key, got {len(private_bytes)} bytes")

        if not save_path:
            from ciris_engine.logic.utils.path_resolution import get_data_dir

            save_path = get_data_dir() / "agent_signing.key"

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(private_bytes)
            import os

            os.chmod(save_path, 0o600)
            logger.info(f"Saved provisioned key fallback to {save_path}")
        except OSError as e:
            logger.warning(f"Could not save provisioned key to {save_path}: {e}")

        # Path 1: Import directly into CIRISVerify vault (preferred)
        # This is the 2.0 requirement - portal keys go into secure storage
        try:
            verify_signer = CIRISVerifySigner()
            # Initialize client on large stack (required for Android JNI)
            import threading

            import_result: list[Any] = [None, None, None]  # [success, pub_key, error]

            def _import_on_large_stack() -> None:
                try:
                    from ciris_verify import CIRISVerify

                    client = CIRISVerify(skip_integrity_check=True)
                    # Import the portal-issued key (algorithm=2 for Ed25519)
                    client.import_key_sync(private_bytes)
                    # Validate by fetching public key
                    pub_key, algo = client.get_ed25519_public_key_sync()
                    import_result[0] = client
                    import_result[1] = pub_key
                except Exception as e:
                    import_result[2] = e

            thread = threading.Thread(target=_import_on_large_stack)
            thread.start()
            thread.join(timeout=10.0)

            if import_result[2] is not None:
                raise import_result[2]

            if import_result[0] is not None and import_result[1] is not None:
                # Successfully imported into ciris_verify
                verify_signer._client = import_result[0]
                verify_signer._public_key_cache = import_result[1]
                verify_signer._key_id = verify_signer._compute_key_id(import_result[1])
                self._signer = verify_signer
                self._initialized = True
                logger.info(f"Imported portal key into CIRISVerify vault (key_id={verify_signer.key_id})")

                # Delete the disk fallback - we don't need it anymore
                try:
                    if save_path.exists():
                        save_path.unlink()
                        logger.debug(f"Deleted disk fallback after successful ciris_verify import")
                except Exception as e:
                    logger.debug(f"Could not delete disk fallback {save_path}: {e}")
                return
        except Exception as e:
            logger.debug(f"CIRISVerify import not available for provisioned key: {e}")

        # Path 2: Ed25519 fallback with the provisioned key (disk-based)
        self._signer = Ed25519Signer()
        self._signer._private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
        self._signer._public_key = self._signer._private_key.public_key()
        self._signer._key_id = self._signer._compute_key_id(self._signer.public_key_bytes)
        self._key_path = save_path
        self._initialized = True
        logger.info(f"Using Ed25519 fallback for provisioned key (key_id={self._signer._key_id})")

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

        Returns dict suitable for POST to /api/v1/accord/public-keys
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

    This ensures all components (audit, accord metrics, etc.)
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
