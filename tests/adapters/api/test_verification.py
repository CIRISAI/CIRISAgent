"""Comprehensive tests for deletion verification API endpoints."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.services.governance.dsar.signature_service import (
    DeletionProof,
    RSASignatureService,
    SignatureVerificationResult,
)


@pytest.fixture
def signature_service():
    """Create real signature service for testing."""
    from ciris_engine.logic.adapters.api.routes import verification

    # Create new service
    service = RSASignatureService()

    # Inject it into the verification module's global
    verification._signature_service = service

    yield service

    # Clean up after test
    verification._signature_service = None


@pytest.fixture
def valid_deletion_proof(signature_service):
    """Create a valid deletion proof."""
    return signature_service.sign_deletion(
        deletion_id="DEL-TEST-001",
        user_identifier="test@example.com",
        sources_deleted={
            "ciris": {"records_deleted": 10, "tables": ["users", "consent"]},
            "sql_db_1": {"records_deleted": 5, "tables": ["user_data"]},
        },
        deleted_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def client():
    """Create test client (no auth required for verification endpoints)."""
    app = create_app()
    return TestClient(app)


class TestVerifyDeletionProof:
    """Test deletion proof verification endpoint."""

    def test_verify_valid_proof(self, client, valid_deletion_proof):
        """Test verifying a valid deletion proof."""
        request_data = {"deletion_proof": valid_deletion_proof.model_dump()}

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["valid"] is True
        assert data["data"]["deletion_id"] == "DEL-TEST-001"
        assert data["data"]["user_identifier"] == "test@example.com"
        assert "verified" in data["data"]["message"].lower()

    def test_verify_tampered_proof(self, client, valid_deletion_proof):
        """Test that tampered proof is rejected."""
        # Tamper with the proof
        tampered_proof = valid_deletion_proof.model_copy()
        tampered_proof.sources_deleted["ciris"]["records_deleted"] = 999

        request_data = {"deletion_proof": tampered_proof.model_dump()}

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["valid"] is False

    def test_verify_invalid_signature(self, client, valid_deletion_proof):
        """Test that invalid signature is rejected."""
        invalid_proof = valid_deletion_proof.model_copy()
        invalid_proof.signature = "INVALID_SIGNATURE_BASE64=="

        request_data = {"deletion_proof": invalid_proof.model_dump()}

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["valid"] is False

    def test_verify_requires_no_authentication(self, client, valid_deletion_proof):
        """Test that verification is public (no auth required)."""
        request_data = {"deletion_proof": valid_deletion_proof.model_dump()}

        # No authentication headers
        response = client.post("/v1/verification/deletion", json=request_data)

        # Should succeed without auth
        assert response.status_code == status.HTTP_200_OK

    def test_verify_returns_complete_metadata(self, client, valid_deletion_proof):
        """Test that verification returns complete metadata."""
        request_data = {"deletion_proof": valid_deletion_proof.model_dump()}

        response = client.post("/v1/verification/deletion", json=request_data)

        data = response.json()["data"]
        assert "deletion_id" in data
        assert "user_identifier" in data
        assert "deleted_at" in data
        assert "sources_count" in data
        assert "total_records" in data
        assert "message" in data
        assert "verified_at" in data
        assert data["sources_count"] == 2  # ciris + sql_db_1

    def test_verify_invalid_request_format(self, client):
        """Test verification with invalid request format."""
        request_data = {"deletion_proof": {"invalid": "data"}}

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestPublicVerificationPage:
    """Test public verification page endpoint."""

    def test_get_public_verification_page(self, client):
        """Test getting public verification HTML page."""
        deletion_id = "DEL-TEST-001"

        response = client.get(f"/v1/verification/public/{deletion_id}")

        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert deletion_id in response.text
        assert "Deletion Verification" in response.text
        assert "GDPR" in response.text

    def test_public_page_requires_no_authentication(self, client):
        """Test that public page requires no authentication."""
        deletion_id = "DEL-TEST-001"

        # No authentication headers
        response = client.get(f"/v1/verification/public/{deletion_id}")

        assert response.status_code == status.HTTP_200_OK

    def test_public_page_includes_instructions(self, client):
        """Test that public page includes verification instructions."""
        deletion_id = "DEL-TEST-001"

        response = client.get(f"/v1/verification/public/{deletion_id}")

        # Check for key instructions
        assert "How to Verify" in response.text
        assert "/v1/verification/deletion" in response.text
        assert "Manual Verification" in response.text


class TestDownloadPublicKey:
    """Test public key download endpoint."""

    def test_download_current_public_key(self, client, signature_service):
        """Test downloading the current public key."""
        key_id = signature_service.get_public_key_id()

        response = client.get(f"/v1/verification/keys/{key_id}.pub")

        assert response.status_code == status.HTTP_200_OK
        assert "application/x-pem-file" in response.headers["content-type"]
        assert "-----BEGIN PUBLIC KEY-----" in response.text
        assert "-----END PUBLIC KEY-----" in response.text
        assert f"{key_id}.pub" in response.headers["content-disposition"]

    def test_download_nonexistent_key_fails(self, client):
        """Test downloading non-existent public key."""
        response = client.get("/v1/verification/keys/NONEXISTENT_KEY.pub")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_requires_no_authentication(self, client, signature_service):
        """Test that public key download requires no authentication."""
        key_id = signature_service.get_public_key_id()

        # No authentication headers
        response = client.get(f"/v1/verification/keys/{key_id}.pub")

        assert response.status_code == status.HTTP_200_OK


class TestManualSignatureVerification:
    """Test manual signature verification endpoint."""

    def test_manual_verification_success(self, client, valid_deletion_proof):
        """Test manual signature verification."""
        request_data = {
            "deletion_id": valid_deletion_proof.deletion_id,
            "user_identifier": valid_deletion_proof.user_identifier,
            "verification_hash": valid_deletion_proof.verification_hash,
            "signature": valid_deletion_proof.signature,
            "public_key_id": valid_deletion_proof.public_key_id,
        }

        response = client.post("/v1/verification/verify-signature", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["valid"] is True
        assert data["metadata"]["manual_verification"] is True

    def test_manual_verification_invalid_hash(self, client, valid_deletion_proof):
        """Test manual verification with wrong hash."""
        request_data = {
            "deletion_id": valid_deletion_proof.deletion_id,
            "user_identifier": valid_deletion_proof.user_identifier,
            "verification_hash": "0" * 64,  # Wrong hash
            "signature": valid_deletion_proof.signature,
            "public_key_id": valid_deletion_proof.public_key_id,
        }

        response = client.post("/v1/verification/verify-signature", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["valid"] is False

    def test_manual_verification_requires_no_authentication(self, client, valid_deletion_proof):
        """Test that manual verification requires no authentication."""
        request_data = {
            "deletion_id": valid_deletion_proof.deletion_id,
            "user_identifier": valid_deletion_proof.user_identifier,
            "verification_hash": valid_deletion_proof.verification_hash,
            "signature": valid_deletion_proof.signature,
            "public_key_id": valid_deletion_proof.public_key_id,
        }

        # No authentication headers
        response = client.post("/v1/verification/verify-signature", json=request_data)

        assert response.status_code == status.HTTP_200_OK


class TestGetCurrentPublicKeyInfo:
    """Test current public key info endpoint."""

    def test_get_current_key_info(self, client, signature_service):
        """Test getting current public key information."""
        response = client.get("/v1/verification/keys/current")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "public_key_id" in data["data"]
        assert "download_url" in data["data"]
        assert "algorithm" in data["data"]
        assert "key_size" in data["data"]
        assert data["data"]["algorithm"] == "RSA-PSS with SHA-256"
        assert data["data"]["key_size"] == 2048

    def test_get_current_key_info_requires_no_authentication(self, client):
        """Test that key info endpoint requires no authentication."""
        # No authentication headers
        response = client.get("/v1/verification/keys/current")

        assert response.status_code == status.HTTP_200_OK


class TestVerificationIntegration:
    """Integration tests for verification flow."""

    def test_complete_verification_flow(self, client, signature_service):
        """Test complete verification flow from signing to verification."""
        # 1. Sign a deletion
        proof = signature_service.sign_deletion(
            deletion_id="INTEGRATION-001",
            user_identifier="integration@example.com",
            sources_deleted={
                "ciris": {"records": 20},
                "external": {"records": 10},
            },
            deleted_at=datetime.now(timezone.utc),
        )

        # 2. Verify the deletion proof
        verify_response = client.post(
            "/v1/verification/deletion", json={"deletion_proof": proof.model_dump()}
        )
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.json()["data"]["valid"] is True

        # 3. Get current key info
        key_info_response = client.get("/v1/verification/keys/current")
        assert key_info_response.status_code == status.HTTP_200_OK
        key_id = key_info_response.json()["data"]["public_key_id"]

        # 4. Download public key
        key_response = client.get(f"/v1/verification/keys/{key_id}.pub")
        assert key_response.status_code == status.HTTP_200_OK

        # 5. Manual verification
        manual_response = client.post(
            "/v1/verification/verify-signature",
            json={
                "deletion_id": proof.deletion_id,
                "user_identifier": proof.user_identifier,
                "verification_hash": proof.verification_hash,
                "signature": proof.signature,
                "public_key_id": proof.public_key_id,
            },
        )
        assert manual_response.status_code == status.HTTP_200_OK
        assert manual_response.json()["data"]["valid"] is True

    def test_user_verification_workflow(self, client, signature_service):
        """Test typical user verification workflow."""
        # User receives deletion proof after DSAR deletion
        proof = signature_service.sign_deletion(
            deletion_id="USER-WORKFLOW-001",
            user_identifier="user@example.com",
            sources_deleted={
                "ciris": {"records_deleted": 15, "decay_started": True},
                "sql_db": {"records_deleted": 8, "verified": True},
            },
            deleted_at=datetime.now(timezone.utc),
        )

        # User visits public verification page
        public_page_response = client.get(f"/v1/verification/public/{proof.deletion_id}")
        assert public_page_response.status_code == status.HTTP_200_OK

        # User submits proof for verification
        verify_response = client.post(
            "/v1/verification/deletion", json={"deletion_proof": proof.model_dump()}
        )
        assert verify_response.status_code == status.HTTP_200_OK

        # Verification result confirms deletion
        data = verify_response.json()["data"]
        assert data["valid"] is True
        assert data["sources_count"] == 2
        assert data["total_records"] == 23  # 15 + 8

    def test_independent_verification_workflow(self, client, signature_service):
        """Test independent verification using downloaded public key."""
        # Sign deletion
        proof = signature_service.sign_deletion(
            deletion_id="INDEPENDENT-001",
            user_identifier="verify@example.com",
            sources_deleted={"ciris": {"records": 10}},
            deleted_at=datetime.now(timezone.utc),
        )

        # Get current key info
        key_info = client.get("/v1/verification/keys/current").json()["data"]

        # Download public key (user can verify offline with this)
        key_response = client.get(key_info["download_url"])
        assert key_response.status_code == status.HTTP_200_OK

        # Manual verification using hash and signature
        manual_verify = client.post(
            "/v1/verification/verify-signature",
            json={
                "deletion_id": proof.deletion_id,
                "user_identifier": proof.user_identifier,
                "verification_hash": proof.verification_hash,
                "signature": proof.signature,
                "public_key_id": proof.public_key_id,
            },
        )
        assert manual_verify.json()["data"]["valid"] is True


class TestVerificationErrorHandling:
    """Test error handling in verification endpoints."""

    def test_verify_with_malformed_proof(self, client):
        """Test verification with malformed proof data."""
        request_data = {
            "deletion_proof": {
                "deletion_id": "TEST",
                # Missing required fields
            }
        }

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_manual_verify_with_missing_fields(self, client):
        """Test manual verification with missing fields."""
        request_data = {
            "deletion_id": "TEST",
            # Missing other required fields
        }

        response = client.post("/v1/verification/verify-signature", json=request_data)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
