"""RSA signature service for DSAR deletion proofs.

Provides cryptographic verification of data deletion using RSA-PSS signatures.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DeletionProof(BaseModel):
    """Cryptographically signed proof of data deletion."""

    deletion_id: str = Field(..., description="Unique deletion request ID")
    user_identifier: str = Field(..., description="User identifier for deleted data")
    sources_deleted: Dict[str, Any] = Field(..., description="Sources and records deleted")
    deleted_at: str = Field(..., description="ISO 8601 deletion timestamp")
    verification_hash: str = Field(..., description="SHA-256 hash of deletion details")
    signature: str = Field(..., description="RSA-PSS signature (base64)")
    public_key_id: str = Field(..., description="ID of RSA key used for signing")


class SignatureVerificationResult(BaseModel):
    """Result of signature verification."""

    valid: bool = Field(..., description="Whether signature is valid")
    deletion_id: str = Field(..., description="Deletion request ID")
    user_identifier: str = Field(..., description="User identifier")
    deleted_at: str = Field(..., description="Deletion timestamp")
    sources_count: int = Field(..., description="Number of sources deleted")
    total_records: int = Field(..., description="Total records deleted")
    message: str = Field(..., description="Verification result message")
    verified_at: str = Field(..., description="When verification occurred")


class RSASignatureService:
    """Manages RSA key pairs and signing for deletion proofs."""

    def __init__(self, key_size: int = 2048):
        """Initialize signature service.

        Args:
            key_size: RSA key size in bits (default 2048)
        """
        self._key_size = key_size
        self._current_key_pair: Optional[Tuple[RSAPrivateKey, RSAPublicKey]] = None
        self._public_key_id = ""
        self._key_created_at: Optional[datetime] = None

        # Initialize default key pair
        self._generate_key_pair()

    def _generate_key_pair(self) -> None:
        """Generate new RSA key pair."""
        logger.info(f"Generating RSA-{self._key_size} key pair for deletion signatures")

        private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=self._key_size, backend=default_backend()
        )

        public_key = private_key.public_key()

        self._current_key_pair = (private_key, public_key)
        self._key_created_at = datetime.now(timezone.utc)
        self._public_key_id = self._key_created_at.strftime("KEY_%Y%m%d_%H%M%S")

        logger.info(f"RSA key pair generated: {self._public_key_id}")

    def get_public_key_pem(self) -> str:
        """Get current public key in PEM format.

        Returns:
            Public key as PEM-encoded string
        """
        if not self._current_key_pair:
            raise RuntimeError("No key pair available")

        _, public_key = self._current_key_pair

        pem_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        return pem_bytes.decode("utf-8")

    def get_public_key_id(self) -> str:
        """Get current public key ID.

        Returns:
            Public key identifier
        """
        return self._public_key_id

    def _compute_deletion_hash(self, deletion_data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of deletion data.

        Args:
            deletion_data: Deletion details to hash

        Returns:
            Hex-encoded SHA-256 hash
        """
        # Serialize to deterministic JSON
        json_data = json.dumps(deletion_data, sort_keys=True, separators=(",", ":"))
        hash_obj = hashlib.sha256(json_data.encode("utf-8"))
        return hash_obj.hexdigest()

    def sign_deletion(
        self, deletion_id: str, user_identifier: str, sources_deleted: Dict[str, Any], deleted_at: datetime
    ) -> DeletionProof:
        """Create cryptographically signed deletion proof.

        Args:
            deletion_id: Unique deletion request ID
            user_identifier: User identifier
            sources_deleted: Dictionary of sources and deletion details
            deleted_at: Deletion timestamp

        Returns:
            Signed deletion proof
        """
        if not self._current_key_pair:
            raise RuntimeError("No key pair available for signing")

        private_key, _ = self._current_key_pair

        # Build deletion data structure
        deletion_data = {
            "deletion_id": deletion_id,
            "user_identifier": user_identifier,
            "sources_deleted": sources_deleted,
            "deleted_at": deleted_at.isoformat(),
        }

        # Compute hash
        verification_hash = self._compute_deletion_hash(deletion_data)

        # Sign the hash using RSA-PSS
        signature_bytes = private_key.sign(
            verification_hash.encode("utf-8"),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )

        # Base64 encode signature
        import base64

        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

        logger.info(f"Deletion proof signed: {deletion_id} using key {self._public_key_id}")

        return DeletionProof(
            deletion_id=deletion_id,
            user_identifier=user_identifier,
            sources_deleted=sources_deleted,
            deleted_at=deleted_at.isoformat(),
            verification_hash=verification_hash,
            signature=signature_b64,
            public_key_id=self._public_key_id,
        )

    def verify_deletion(self, proof: DeletionProof) -> SignatureVerificationResult:
        """Verify cryptographic signature on deletion proof.

        Args:
            proof: Deletion proof to verify

        Returns:
            Verification result
        """
        import base64

        verified_at = datetime.now(timezone.utc)

        try:
            if not self._current_key_pair:
                return SignatureVerificationResult(
                    valid=False,
                    deletion_id=proof.deletion_id,
                    user_identifier=proof.user_identifier,
                    deleted_at=proof.deleted_at,
                    sources_count=len(proof.sources_deleted),
                    total_records=0,
                    message="No public key available for verification",
                    verified_at=verified_at.isoformat(),
                )

            _, public_key = self._current_key_pair

            # Recompute hash
            deletion_data = {
                "deletion_id": proof.deletion_id,
                "user_identifier": proof.user_identifier,
                "sources_deleted": proof.sources_deleted,
                "deleted_at": proof.deleted_at,
            }

            computed_hash = self._compute_deletion_hash(deletion_data)

            # Check hash matches
            if computed_hash != proof.verification_hash:
                return SignatureVerificationResult(
                    valid=False,
                    deletion_id=proof.deletion_id,
                    user_identifier=proof.user_identifier,
                    deleted_at=proof.deleted_at,
                    sources_count=len(proof.sources_deleted),
                    total_records=0,
                    message="Hash mismatch - deletion data may have been tampered with",
                    verified_at=verified_at.isoformat(),
                )

            # Decode signature
            signature_bytes = base64.b64decode(proof.signature)

            # Verify RSA-PSS signature
            try:
                public_key.verify(
                    signature_bytes,
                    computed_hash.encode("utf-8"),
                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                    hashes.SHA256(),
                )

                # Signature is valid
                total_records = sum(source.get("total_records_deleted", 0) for source in proof.sources_deleted.values())

                logger.info(f"Deletion proof verified successfully: {proof.deletion_id}")

                return SignatureVerificationResult(
                    valid=True,
                    deletion_id=proof.deletion_id,
                    user_identifier=proof.user_identifier,
                    deleted_at=proof.deleted_at,
                    sources_count=len(proof.sources_deleted),
                    total_records=total_records,
                    message="Deletion proof verified - signature valid",
                    verified_at=verified_at.isoformat(),
                )

            except Exception as sig_error:
                logger.warning(f"Signature verification failed for {proof.deletion_id}: {sig_error}")
                return SignatureVerificationResult(
                    valid=False,
                    deletion_id=proof.deletion_id,
                    user_identifier=proof.user_identifier,
                    deleted_at=proof.deleted_at,
                    sources_count=len(proof.sources_deleted),
                    total_records=0,
                    message="Invalid signature - deletion proof cannot be verified",
                    verified_at=verified_at.isoformat(),
                )

        except Exception as e:
            logger.error(f"Error verifying deletion proof {proof.deletion_id}: {e}")
            return SignatureVerificationResult(
                valid=False,
                deletion_id=proof.deletion_id,
                user_identifier=proof.user_identifier,
                deleted_at=proof.deleted_at,
                sources_count=0,
                total_records=0,
                message=f"Verification error: {str(e)}",
                verified_at=verified_at.isoformat(),
            )

    def rotate_keys(self) -> None:
        """Rotate RSA key pair (for periodic security maintenance).

        Old public keys should be retained for historical verification.
        """
        logger.warning(f"Rotating RSA keys - old key ID: {self._public_key_id}")
        self._generate_key_pair()
