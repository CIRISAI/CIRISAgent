"""Comprehensive tests for RSA signature service."""

from datetime import datetime, timezone

import pytest

from ciris_engine.logic.services.governance.dsar.signature_service import (
    DeletionProof,
    RSASignatureService,
    SignatureVerificationResult,
)


class TestRSASignatureServiceInitialization:
    """Test RSA signature service initialization."""

    def test_initialization_creates_key_pair(self):
        """Test that initialization generates RSA key pair."""
        service = RSASignatureService()

        assert service._current_key_pair is not None
        assert service._public_key_id != ""
        assert service._key_created_at is not None

    def test_initialization_with_custom_key_size(self):
        """Test initialization with custom key size."""
        service = RSASignatureService(key_size=4096)

        # Should still work, just with larger key
        assert service._key_size == 4096
        assert service._current_key_pair is not None

    def test_get_public_key_pem_returns_valid_pem(self):
        """Test that public key PEM is valid format."""
        service = RSASignatureService()

        pem = service.get_public_key_pem()

        assert pem.startswith("-----BEGIN PUBLIC KEY-----")
        assert pem.endswith("-----END PUBLIC KEY-----\n")
        assert isinstance(pem, str)

    def test_get_public_key_id_returns_consistent_id(self):
        """Test that public key ID is consistent."""
        service = RSASignatureService()

        key_id_1 = service.get_public_key_id()
        key_id_2 = service.get_public_key_id()

        assert key_id_1 == key_id_2
        assert key_id_1.startswith("KEY_")


class TestDeletionProofSigning:
    """Test deletion proof signing."""

    @pytest.fixture
    def service(self):
        """Create signature service."""
        return RSASignatureService()

    @pytest.fixture
    def sample_deletion_data(self):
        """Sample deletion data."""
        return {
            "deletion_id": "DEL-TEST-001",
            "user_identifier": "test@example.com",
            "sources_deleted": {
                "ciris": {"records": 5, "tables": ["users", "consent"]},
                "external_db": {"records": 10, "tables": ["user_data"]},
            },
            "deleted_at": datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        }

    def test_sign_deletion_returns_proof(self, service, sample_deletion_data):
        """Test that signing returns a valid proof."""
        proof = service.sign_deletion(
            deletion_id=sample_deletion_data["deletion_id"],
            user_identifier=sample_deletion_data["user_identifier"],
            sources_deleted=sample_deletion_data["sources_deleted"],
            deleted_at=sample_deletion_data["deleted_at"],
        )

        assert isinstance(proof, DeletionProof)
        assert proof.deletion_id == sample_deletion_data["deletion_id"]
        assert proof.user_identifier == sample_deletion_data["user_identifier"]
        assert proof.sources_deleted == sample_deletion_data["sources_deleted"]
        assert proof.signature != ""
        assert proof.verification_hash != ""
        assert proof.public_key_id == service.get_public_key_id()

    def test_sign_deletion_creates_unique_signatures(self, service):
        """Test that different data produces different signatures."""
        deleted_at = datetime.now(timezone.utc)

        proof1 = service.sign_deletion(
            deletion_id="DEL-001",
            user_identifier="user1@example.com",
            sources_deleted={"ciris": {"records": 5}},
            deleted_at=deleted_at,
        )

        proof2 = service.sign_deletion(
            deletion_id="DEL-002",
            user_identifier="user2@example.com",
            sources_deleted={"ciris": {"records": 10}},
            deleted_at=deleted_at,
        )

        assert proof1.signature != proof2.signature
        assert proof1.verification_hash != proof2.verification_hash

    def test_sign_deletion_deterministic_hash(self, service, sample_deletion_data):
        """Test that same data produces same hash."""
        proof1 = service.sign_deletion(
            deletion_id=sample_deletion_data["deletion_id"],
            user_identifier=sample_deletion_data["user_identifier"],
            sources_deleted=sample_deletion_data["sources_deleted"],
            deleted_at=sample_deletion_data["deleted_at"],
        )

        proof2 = service.sign_deletion(
            deletion_id=sample_deletion_data["deletion_id"],
            user_identifier=sample_deletion_data["user_identifier"],
            sources_deleted=sample_deletion_data["sources_deleted"],
            deleted_at=sample_deletion_data["deleted_at"],
        )

        # Hash should be deterministic
        assert proof1.verification_hash == proof2.verification_hash


class TestDeletionProofVerification:
    """Test deletion proof verification."""

    @pytest.fixture
    def service(self):
        """Create signature service."""
        return RSASignatureService()

    @pytest.fixture
    def valid_proof(self, service):
        """Create a valid signed proof."""
        return service.sign_deletion(
            deletion_id="DEL-TEST-001",
            user_identifier="test@example.com",
            sources_deleted={"ciris": {"records": 5}},
            deleted_at=datetime.now(timezone.utc),
        )

    def test_verify_deletion_validates_correct_proof(self, service, valid_proof):
        """Test that verification accepts valid proof."""
        result = service.verify_deletion(valid_proof)

        assert isinstance(result, SignatureVerificationResult)
        assert result.valid is True
        assert result.deletion_id == valid_proof.deletion_id
        assert result.user_identifier == valid_proof.user_identifier
        assert "verified" in result.message.lower()

    def test_verify_deletion_rejects_tampered_data(self, service, valid_proof):
        """Test that verification rejects tampered data."""
        # Tamper with sources_deleted
        tampered_proof = valid_proof.model_copy()
        tampered_proof.sources_deleted["ciris"]["records"] = 999

        result = service.verify_deletion(tampered_proof)

        assert result.valid is False
        assert "hash mismatch" in result.message.lower() or "tampered" in result.message.lower()

    def test_verify_deletion_rejects_invalid_signature(self, service, valid_proof):
        """Test that verification rejects invalid signature."""
        # Replace signature with garbage
        tampered_proof = valid_proof.model_copy()
        tampered_proof.signature = "INVALID_SIGNATURE_BASE64=="

        result = service.verify_deletion(tampered_proof)

        assert result.valid is False
        assert "invalid" in result.message.lower() or "cannot be verified" in result.message.lower()

    def test_verify_deletion_rejects_wrong_hash(self, service, valid_proof):
        """Test that verification rejects proof with wrong hash."""
        tampered_proof = valid_proof.model_copy()
        tampered_proof.verification_hash = "0" * 64  # Wrong hash

        result = service.verify_deletion(tampered_proof)

        assert result.valid is False

    def test_verify_deletion_includes_metadata(self, service, valid_proof):
        """Test that verification result includes complete metadata."""
        result = service.verify_deletion(valid_proof)

        assert result.deletion_id == valid_proof.deletion_id
        assert result.user_identifier == valid_proof.user_identifier
        assert result.deleted_at == valid_proof.deleted_at
        assert result.sources_count == len(valid_proof.sources_deleted)
        assert result.verified_at is not None


class TestKeyRotation:
    """Test key rotation functionality."""

    def test_rotate_keys_changes_key_id(self):
        """Test that key rotation changes the public key ID."""
        import time

        service = RSASignatureService()

        old_key_id = service.get_public_key_id()

        # Wait 1 second to ensure timestamp differs
        time.sleep(1)

        # Rotate keys
        service.rotate_keys()

        new_key_id = service.get_public_key_id()

        assert old_key_id != new_key_id

    def test_rotate_keys_changes_public_key(self):
        """Test that key rotation changes the public key."""
        service = RSASignatureService()

        old_pem = service.get_public_key_pem()

        # Rotate keys
        service.rotate_keys()

        new_pem = service.get_public_key_pem()

        assert old_pem != new_pem

    def test_old_proofs_fail_after_rotation(self):
        """Test that proofs signed with old key fail after rotation."""
        service = RSASignatureService()

        # Sign proof with original key
        proof = service.sign_deletion(
            deletion_id="DEL-001",
            user_identifier="test@example.com",
            sources_deleted={"ciris": {"records": 5}},
            deleted_at=datetime.now(timezone.utc),
        )

        # Verify with original key (should succeed)
        result1 = service.verify_deletion(proof)
        assert result1.valid is True

        # Rotate keys
        service.rotate_keys()

        # Verify with new key (should fail - different key)
        result2 = service.verify_deletion(proof)
        assert result2.valid is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_sign_deletion_with_empty_sources(self):
        """Test signing with empty sources."""
        service = RSASignatureService()

        proof = service.sign_deletion(
            deletion_id="DEL-EMPTY",
            user_identifier="test@example.com",
            sources_deleted={},  # Empty
            deleted_at=datetime.now(timezone.utc),
        )

        # Should still create valid proof
        assert proof.signature != ""
        assert proof.verification_hash != ""

        # Should verify successfully
        result = service.verify_deletion(proof)
        assert result.valid is True

    def test_sign_deletion_with_complex_nested_data(self):
        """Test signing with complex nested data structures."""
        service = RSASignatureService()

        complex_sources = {
            "ciris": {
                "records": 100,
                "tables": ["users", "consent", "interactions"],
                "metadata": {"decay_started": "2025-01-15", "completion": 90},
            },
            "sql_db_1": {
                "records": 50,
                "verified": True,
                "details": {"host": "db.example.com", "port": 5432},
            },
        }

        proof = service.sign_deletion(
            deletion_id="DEL-COMPLEX",
            user_identifier="test@example.com",
            sources_deleted=complex_sources,
            deleted_at=datetime.now(timezone.utc),
        )

        # Should handle complex data
        result = service.verify_deletion(proof)
        assert result.valid is True

    def test_verify_deletion_with_unicode_identifiers(self):
        """Test verification with Unicode user identifiers."""
        service = RSASignatureService()

        proof = service.sign_deletion(
            deletion_id="DEL-UNICODE",
            user_identifier="用户@例え.jp",  # Unicode email
            sources_deleted={"ciris": {"records": 1}},
            deleted_at=datetime.now(timezone.utc),
        )

        result = service.verify_deletion(proof)
        assert result.valid is True
        assert result.user_identifier == "用户@例え.jp"


class TestHashingConsistency:
    """Test hashing consistency."""

    def test_hash_computation_is_deterministic(self):
        """Test that hash computation produces same result."""
        service = RSASignatureService()

        deletion_data = {
            "deletion_id": "DEL-001",
            "user_identifier": "test@example.com",
            "sources_deleted": {"ciris": {"records": 5}},
            "deleted_at": "2025-01-15T12:00:00+00:00",
        }

        hash1 = service._compute_deletion_hash(deletion_data)
        hash2 = service._compute_deletion_hash(deletion_data)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_hash_changes_with_data(self):
        """Test that different data produces different hash."""
        service = RSASignatureService()

        data1 = {"deletion_id": "DEL-001", "user_identifier": "user1@example.com"}
        data2 = {"deletion_id": "DEL-002", "user_identifier": "user2@example.com"}

        hash1 = service._compute_deletion_hash(data1)
        hash2 = service._compute_deletion_hash(data2)

        assert hash1 != hash2


class TestSignatureServiceIntegration:
    """Integration tests for complete sign-verify flow."""

    def test_complete_flow_access_request(self):
        """Test complete flow for access request deletion proof."""
        service = RSASignatureService()

        # Simulate multi-source access request completion
        proof = service.sign_deletion(
            deletion_id="ACCESS-2025-001",
            user_identifier="user@example.com",
            sources_deleted={
                "ciris": {"type": "access", "total_records_deleted": 15},
                "external_db": {"type": "access", "total_records_deleted": 8},
            },
            deleted_at=datetime.now(timezone.utc),
        )

        # User receives proof and verifies it
        result = service.verify_deletion(proof)

        assert result.valid is True
        assert result.total_records == 23  # 15 + 8

    def test_complete_flow_deletion_request(self):
        """Test complete flow for deletion request proof."""
        service = RSASignatureService()

        # Simulate multi-source deletion
        proof = service.sign_deletion(
            deletion_id="DELETE-2025-001",
            user_identifier="user@example.com",
            sources_deleted={
                "ciris": {"records_deleted": 20, "decay_started": True},
                "sql_db_1": {"records_deleted": 10, "verified": True},
                "sql_db_2": {"records_deleted": 5, "verified": True},
            },
            deleted_at=datetime.now(timezone.utc),
        )

        # User verifies deletion occurred
        result = service.verify_deletion(proof)

        assert result.valid is True
        assert result.sources_count == 3
        assert "verified" in result.message.lower()
