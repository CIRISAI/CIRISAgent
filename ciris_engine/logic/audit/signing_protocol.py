"""
Algorithm-agnostic signing protocol for audit and trace signing.

CIRISVerify is the ONLY source of signing keys. All key management goes through
the CIRISVerify singleton which handles:
- Hardware-backed storage (TPM, Android Keystore, iOS Keychain)
- Software fallback (Ed25519 in memory, persisted by Rust)
- Key import from Portal during first-run setup

The protocol supports verification of historical signatures using different algorithms:
- RSA-2048-PSS (legacy, verification only)
- Ed25519 (current default)
- Future: PQC algorithms (ML-DSA/SLH-DSA)
"""

import base64
import hashlib
import logging
from abc import ABC, abstractmethod
from enum import Enum
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

    def _compute_key_id(self, public_key_bytes: bytes) -> str:
        """Compute key ID from public key bytes.

        Format: agent-{sha256(pubkey)[:12]}
        This matches the accord metrics key_id format.
        """
        return f"agent-{hashlib.sha256(public_key_bytes).hexdigest()[:12]}"


class CIRISVerifySigner(BaseSigner):
    """Signing implementation that delegates to CIRISVerify.

    CIRISVerify is the ONLY source of signing keys. It handles:
    - Hardware-backed storage (TPM, Android Keystore, iOS Keychain)
    - Software fallback (Ed25519 in memory, persisted by Rust to CIRIS_DATA_DIR)
    - Key import from Portal during first-run setup

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
        """Sign data via CIRISVerify FFI.

        CIRISVerify handles all key management - if no key exists, it creates
        an ephemeral one automatically.
        """
        if not self._client:
            raise RuntimeError(SIGNER_NOT_INITIALIZED)
        try:
            signature = cast(bytes, self._client.sign_ed25519_sync(data))

            # If we didn't have the public key cached, fetch it now
            if self._public_key_cache is None:
                try:
                    self._public_key_cache = self._client.get_ed25519_public_key_sync()
                    self._algo_name = "Ed25519"
                    self._key_id = self._compute_key_id(self._public_key_cache)
                    logger.info(f"CIRISVerify created key (key_id={self._key_id})")
                except Exception:
                    pass  # Public key fetch is optional for signing

            return signature
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

    def _try_generate_key_with_retry(self, client: Any) -> bool:
        """Try to generate an ephemeral Ed25519 key with singleton reset on failure.

        Args:
            client: CIRISVerify client instance

        Returns:
            True if key generation succeeded, False if failed after retry
        """
        import time

        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
            get_verifier,
            reset_verifier,
        )

        for attempt in range(2):  # Try twice: original + one retry after reset
            try:
                logger.info(f"[signing] Attempting key generation (attempt {attempt + 1}/2)")
                client.generate_key_sync()  # type: ignore[attr-defined, unused-ignore]
                logger.info("[signing] Ephemeral Ed25519 key generated successfully")
                return True
            except Exception as e:
                logger.error(f"[signing] Key generation failed (attempt {attempt + 1}/2): {e}")

                if attempt == 0:
                    # First failure - try resetting the singleton and getting fresh client
                    logger.warning("[signing] Resetting CIRISVerify singleton and retrying...")
                    try:
                        reset_verifier()
                        time.sleep(0.5)  # Brief pause before retry
                        client = get_verifier()
                        self._client = client
                    except Exception as reset_error:
                        logger.error(f"[signing] Singleton reset failed: {reset_error}")
                        return False
                else:
                    # Second failure - give up
                    logger.error(
                        "[signing] FATAL: Key generation failed after singleton reset. "
                        "Native library or keystore issue."
                    )
                    return False

        return False

    def initialize(self) -> bool:
        """Initialize from CIRISVerify singleton.

        Returns True if CIRISVerify has a key available, False if waiting for Portal import.
        Retries with backoff if attestation is in progress (AttestationInProgressError).
        """
        import time

        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        # Import the attestation-in-progress exception if available
        # (may not exist in all versions of ciris_verify)
        AttestationInProgressError: type | None = None
        try:
            import ciris_adapters.ciris_verify as ciris_verify

            if hasattr(ciris_verify, "AttestationInProgressError"):
                AttestationInProgressError = ciris_verify.AttestationInProgressError
        except ImportError:
            pass

        # Retry with backoff when attestation is running
        max_retries = 10
        base_delay = 0.5  # Start with 500ms delay

        for attempt in range(max_retries):
            try:
                client = get_verifier()
                if client is None:
                    logger.debug("CIRISVerify singleton not available")
                    return False

                self._client = client

                # Check if key exists in secure storage
                has_key = client.has_key_sync()  # type: ignore[attr-defined, unused-ignore]

                if not has_key:
                    # No key exists - generate ephemeral key (v1.1.17+ fixed catch_unwind)
                    if hasattr(client, "generate_key_sync"):
                        logger.info("[signing] No signing key found, generating ephemeral Ed25519 key")
                        if not self._try_generate_key_with_retry(client):
                            # Key generation failed after retries - fatal error
                            error_msg = (
                                "FATAL: Ed25519 key generation failed after retry. "
                                "The signing system cannot initialize. "
                                "Check ciris_verify native library and Android Keystore access."
                            )
                            logger.error(f"[signing] {error_msg}")
                            raise RuntimeError(error_msg)
                    else:
                        # Older CIRISVerify without generate_key support
                        logger.debug("CIRISVerify initialized but no key available (waiting for Portal import)")
                        return False

                # Key exists (or was just generated), get the public key
                key_bytes = client.get_ed25519_public_key_sync()  # type: ignore[attr-defined, unused-ignore]
                self._public_key_cache = key_bytes
                self._algo_name = "Ed25519"
                self._key_id = self._compute_key_id(key_bytes)
                self._algorithm = SigningAlgorithm.ED25519
                logger.info(f"CIRISVerify signer loaded (algo={self._algo_name}, key_id={self._key_id})")
                return True

            except Exception as e:
                # Check if it's the specific attestation-in-progress error
                is_attestation_busy = (
                    AttestationInProgressError is not None and isinstance(e, AttestationInProgressError)
                ) or "attestation" in str(e).lower()

                if is_attestation_busy and attempt < max_retries - 1:
                    delay = base_delay * (2 ** min(attempt, 4))  # Cap at 8s
                    logger.info(
                        f"Attestation in progress, waiting {delay:.1f}s before retry "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                elif attempt < max_retries - 1:
                    # Other transient error - shorter retry
                    logger.debug(f"CIRISVerify FFI call failed, retrying: {e}")
                    time.sleep(0.1)
                else:
                    logger.warning(f"CIRISVerify not available after {max_retries} attempts: {e}")
                    return False

        return False


class UnifiedSigningKey:
    """Unified signing key management for audit and accord metrics.

    CIRISVerify is the ONLY source of signing keys. All key management goes through
    CIRISVerify which handles hardware/software storage internally.

    Keys are either:
    1. Imported from Portal during first-run setup
    2. Already present in CIRISVerify vault from previous session

    Key ID format: agent-{sha256(pubkey)[:12]}
    """

    def __init__(self) -> None:
        """Initialize unified signing key manager."""
        self._signer: Optional[CIRISVerifySigner] = None
        self._initialized = False
        self._on_key_registered: Optional[Any] = None  # Callback for key registration

    @property
    def signer(self) -> BaseSigner:
        if not self._signer:
            raise RuntimeError("UnifiedSigningKey not initialized - no key available from CIRISVerify")
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

    @property
    def has_key(self) -> bool:
        """Check if a signing key is actually available (not just initialized).

        Returns True only if CIRISVerify has a key loaded or imported.
        Returns False if waiting for Portal import or ephemeral key creation.
        """
        return self._signer is not None and self._initialized and self._signer._key_id is not None

    def initialize(self) -> None:
        """Initialize the signing key from CIRISVerify.

        CIRISVerify is REQUIRED and handles all key management:
        - Hardware-backed keys (TPM, Keystore, Keychain)
        - Software fallback with ephemeral key creation
        - Key persistence

        Raises:
            RuntimeError: If CIRISVerify singleton is not available
        """
        if self._initialized:
            return

        # CIRISVerify is REQUIRED - fail hard if not available
        from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

        client = get_verifier()
        if client is None:
            raise RuntimeError(
                "FATAL: CIRISVerify is not available. "
                "Cannot initialize signing without CIRISVerify singleton. "
                "Ensure ciris_verify is properly installed and initialized."
            )

        verify_signer = CIRISVerifySigner()
        if verify_signer.initialize():
            self._signer = verify_signer
            self._initialized = True
            logger.info(f"Using CIRISVerify for signing (key_id={verify_signer.key_id})")
            # Notify callback that key is available (may be new ephemeral or existing)
            self._notify_key_registered()
        else:
            # CIRISVerify has no key - it will create an ephemeral one when needed
            # Store the client reference so we can use it for signing
            verify_signer._client = client
            self._signer = verify_signer
            self._initialized = True
            logger.info("CIRISVerify ready - will create ephemeral key on first sign")

    def load_provisioned_key(self, ed25519_private_key_b64: str) -> None:
        """DEPRECATED: Load signing key from Portal provisioning.

        This method is DEPRECATED and will raise an error.

        CIRIS now uses SELF-CUSTODY key management (FSD-002):
        - Agent generates its own Ed25519 keypair via CIRISVerify
        - Private key is TPM-protected and NEVER leaves the agent
        - Only the PUBLIC key is registered with Portal
        - Portal NEVER issues or receives private keys

        Args:
            ed25519_private_key_b64: DEPRECATED - not used

        Raises:
            NotImplementedError: Always. Use self-custody flow instead.
        """
        raise NotImplementedError(
            "load_provisioned_key is DEPRECATED (FSD-002 Self-Custody). "
            "Portal no longer issues private keys. Agents generate their own keys "
            "and register the PUBLIC key with Portal. The private key never leaves "
            "the agent. See FSD-002_SELF_CUSTODY_KEYS.md for the new flow."
        )

    def _notify_key_registered(self) -> None:
        """Notify that a key has been registered/changed.

        This triggers registration in audit_signing_keys table via callback.
        The callback is set by AuditSignatureManager during initialization.
        """
        if self._signer and hasattr(self, "_on_key_registered") and self._on_key_registered:
            try:
                self._on_key_registered(
                    key_id=self._signer.key_id,
                    public_key_base64=self._signer.public_key_base64,
                    algorithm="ed25519",
                )
            except Exception as e:
                logger.warning(f"Failed to notify key registration: {e}")

    def set_key_registration_callback(self, callback: Optional[Any]) -> None:
        """Set callback for key registration events.

        Args:
            callback: Function(key_id, public_key_base64, algorithm) to call on key changes
        """
        self._on_key_registered = callback

    def sign(self, data: bytes) -> bytes:
        """Sign data and return signature bytes.

        If CIRISVerify creates an ephemeral key during this sign operation,
        the key is registered in audit_signing_keys via callback.
        """
        # Track if we had a key before signing
        had_key_before = self._signer is not None and self._signer._key_id is not None
        old_key_id = self._signer._key_id if self._signer else None

        signature = self.signer.sign(data)

        # Check if a new key was created during signing (ephemeral key case)
        new_key_id = self._signer._key_id if self._signer else None
        if new_key_id and new_key_id != old_key_id:
            logger.info(f"Ephemeral key created during sign: {new_key_id}")
            self._notify_key_registered()

        return signature

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
        key = UnifiedSigningKey()
        key.initialize()  # If this throws, _unified_key stays None for retry
        _unified_key = key  # Only set global after successful init
    return _unified_key


def reset_unified_signing_key() -> None:
    """Reset the global unified signing key (for testing)."""
    global _unified_key
    _unified_key = None
