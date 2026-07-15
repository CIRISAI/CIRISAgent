"""Tests for deletion verification API endpoints (substrate Ed25519 surface).

The 2.9.7 DRY purge deleted the homegrown RSA-PSS signer; deletion proofs
are now signed/verified via the persist Engine's local Ed25519 identity
(``Engine.local_sign`` / ``Engine.verify_hybrid``) over RFC 8785 (JCS)
canonical bytes. These tests wire a real persist Engine (shared
``persist_engine`` fixture) and drive the full HTTP surface.
"""

from datetime import datetime, timezone

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.routes.verification import DeletionProof, sign_deletion_proof


@pytest.fixture
def client(persist_engine):
    """Test client with a real persist Engine wired (local Ed25519 identity)."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def valid_deletion_proof(persist_engine):
    """Create a valid deletion proof signed by the substrate identity."""
    return sign_deletion_proof(
        deletion_id="DEL-TEST-001",
        user_identifier="test@example.com",
        sources_deleted={
            "ciris": {"total_records_deleted": 10, "tables": ["users", "consent"]},
            "sql_db_1": {"total_records_deleted": 5, "tables": ["user_data"]},
        },
        deleted_at=datetime.now(timezone.utc),
    )


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
        tampered_proof = valid_deletion_proof.model_copy(deep=True)
        tampered_proof.sources_deleted["ciris"]["total_records_deleted"] = 999

        request_data = {"deletion_proof": tampered_proof.model_dump()}

        response = client.post("/v1/verification/deletion", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["valid"] is False

    def test_verify_invalid_signature(self, client, valid_deletion_proof):
        """Test that invalid signature is rejected."""
        invalid_proof = valid_deletion_proof.model_copy(deep=True)
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

        response = client.post("/v1/verification/deletion", json=request_data)

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
        assert data["total_records"] == 15  # 10 + 5

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

    def test_public_page_includes_instructions(self, client):
        """Test that public page includes verification instructions."""
        deletion_id = "DEL-TEST-001"

        response = client.get(f"/v1/verification/public/{deletion_id}")

        assert "How to Verify" in response.text
        assert "/v1/verification/deletion" in response.text
        assert "Manual Verification" in response.text


class TestDownloadPublicKey:
    """Test public key download endpoint."""

    def test_download_current_public_key(self, client, persist_engine):
        """Test downloading the current public key (base64 Ed25519)."""
        key_id = persist_engine.local_derived_key_id()

        response = client.get(f"/v1/verification/keys/{key_id}.pub")

        assert response.status_code == status.HTTP_200_OK
        assert response.text == persist_engine.local_public_key_b64()
        assert f"{key_id}.pub" in response.headers["content-disposition"]

    def test_download_nonexistent_key_fails(self, client):
        """Test downloading non-existent public key."""
        response = client.get("/v1/verification/keys/NONEXISTENT_KEY.pub")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestManualSignatureVerification:
    """Test manual signature verification endpoint."""

    @staticmethod
    def _manual_request(proof: DeletionProof) -> dict:
        return {
            "deletion_id": proof.deletion_id,
            "user_identifier": proof.user_identifier,
            "sources_deleted": proof.sources_deleted,
            "deleted_at": proof.deleted_at,
            "signature": proof.signature,
            "public_key_id": proof.public_key_id,
        }

    def test_manual_verification_success(self, client, valid_deletion_proof):
        """Test manual signature verification."""
        response = client.post("/v1/verification/verify-signature", json=self._manual_request(valid_deletion_proof))

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["valid"] is True
        assert data["metadata"]["manual_verification"] is True

    def test_manual_verification_tampered_data(self, client, valid_deletion_proof):
        """Test manual verification with tampered deletion data."""
        request_data = self._manual_request(valid_deletion_proof)
        request_data["user_identifier"] = "attacker@example.com"

        response = client.post("/v1/verification/verify-signature", json=request_data)

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert data["data"]["valid"] is False


class TestGetCurrentPublicKeyInfo:
    """Test current public key info endpoint."""

    def test_get_current_key_info(self, client, persist_engine):
        """Test getting current public key information."""
        response = client.get("/v1/verification/keys/current")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["data"]["public_key_id"] == persist_engine.local_derived_key_id()
        assert data["data"]["download_url"].endswith(".pub")
        assert "Ed25519" in data["data"]["algorithm"]


class TestVerificationIntegration:
    """Integration tests for verification flow."""

    def test_complete_verification_flow(self, client, persist_engine):
        """Test complete verification flow from signing to verification."""
        # 1. Sign a deletion via the substrate identity
        proof = sign_deletion_proof(
            deletion_id="INTEGRATION-001",
            user_identifier="integration@example.com",
            sources_deleted={
                "ciris": {"total_records_deleted": 20},
                "external": {"total_records_deleted": 10},
            },
            deleted_at=datetime.now(timezone.utc),
        )
        assert proof.public_key_id == persist_engine.local_derived_key_id()

        # 2. Verify the deletion proof
        verify_response = client.post("/v1/verification/deletion", json={"deletion_proof": proof.model_dump()})
        assert verify_response.status_code == status.HTTP_200_OK
        assert verify_response.json()["data"]["valid"] is True
        assert verify_response.json()["data"]["total_records"] == 30

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
                "sources_deleted": proof.sources_deleted,
                "deleted_at": proof.deleted_at,
                "signature": proof.signature,
                "public_key_id": proof.public_key_id,
            },
        )
        assert manual_response.status_code == status.HTTP_200_OK
        assert manual_response.json()["data"]["valid"] is True

    def test_proof_verifiable_offline_with_published_key(self, client, valid_deletion_proof):
        """The downloaded key + JCS canonical bytes verify the proof independently."""
        import base64

        from ciris_verify import jcs_canonicalize

        key_id = valid_deletion_proof.public_key_id
        key_response = client.get(f"/v1/verification/keys/{key_id}.pub")
        assert key_response.status_code == status.HTTP_200_OK

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_response.text))
        canonical = jcs_canonicalize(
            {
                "deletion_id": valid_deletion_proof.deletion_id,
                "user_identifier": valid_deletion_proof.user_identifier,
                "sources_deleted": valid_deletion_proof.sources_deleted,
                "deleted_at": valid_deletion_proof.deleted_at,
            }
        )
        # Raises InvalidSignature on failure
        public_key.verify(base64.b64decode(valid_deletion_proof.signature), canonical)


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
