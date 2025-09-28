"""
Tests for privacy utility functions.

Covers sanitization, PII redaction, and content hashing for anonymous users.
"""

import hashlib
from datetime import datetime, timezone

import pytest

from ciris_engine.logic.utils.privacy import (
    create_refutation_proof,
    redact_personal_info,
    sanitize_audit_details,
    sanitize_correlation_parameters,
    sanitize_for_anonymous,
    sanitize_trace_content,
    should_sanitize_for_user,
    verify_content_hash,
)


class TestPrivacyUtils:
    """Test privacy utility functions."""

    def test_user_id_hashing_consistency(self):
        """Test that user ID hashing is consistent."""
        data1 = {"user_id": "test_user_12345"}
        data2 = {"user_id": "test_user_12345"}

        # Same ID should produce same hash
        sanitized1 = sanitize_for_anonymous(data1)
        sanitized2 = sanitize_for_anonymous(data2)
        assert sanitized1["user_id"] == sanitized2["user_id"]
        assert sanitized1["user_id"].startswith("anon_")
        assert len(sanitized1["user_id"]) == 13  # "anon_" + 8 chars

        # Different IDs should produce different hashes
        data3 = {"user_id": "different_user"}
        sanitized3 = sanitize_for_anonymous(data3)
        assert sanitized3["user_id"] != sanitized1["user_id"]

    def test_redact_personal_info(self):
        """Test PII redaction from text."""
        # Test email redaction
        text_with_email = "Contact me at john.doe@example.com for details"
        redacted = redact_personal_info(text_with_email)
        assert "john.doe@example.com" not in redacted
        assert "[email]" in redacted

        # Test phone number redaction
        text_with_phone = "Call me at 555-123-4567 or (555) 555-1234"
        redacted = redact_personal_info(text_with_phone)
        assert "555-123-4567" not in redacted
        assert "(555) 555-1234" not in redacted
        assert "[phone]" in redacted

        # Test URL redaction
        text_with_url = "Visit https://example.com/personal for info"
        redacted = redact_personal_info(text_with_url)
        assert "example.com" not in redacted
        assert "[url]" in redacted

        # Test Discord mention redaction
        text_with_mention = "Hey <@123456789> check this out"
        redacted = redact_personal_info(text_with_mention)
        assert "<@123456789>" not in redacted
        assert "[mention]" in redacted

        # Test multiple PII types
        complex_text = "Email john@test.com or call 555-1234, see http://example.com"
        redacted = redact_personal_info(complex_text)
        assert "john@test.com" not in redacted
        assert "555-1234" not in redacted
        assert "example.com" not in redacted
        assert "[email]" in redacted
        assert "[phone]" in redacted
        assert "[url]" in redacted

    def test_sanitize_for_anonymous_basic(self):
        """Test basic anonymization of data."""
        data = {
            "user_id": "user_123",
            "message": "Hello, my email is test@example.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"key": "value"},
        }

        sanitized = sanitize_for_anonymous(data)

        # Check user anonymization
        expected_hash = f"anon_{hashlib.sha256('user_123'.encode()).hexdigest()[:8]}"
        assert sanitized["user_id"] == expected_hash

        # Check message sanitization and hashing
        assert "test@example.com" not in sanitized["message"]
        assert "[email]" in sanitized["message"]
        assert "message_hash" in sanitized

        # Check metadata preservation
        assert sanitized["metadata"] == {"key": "value"}

        # Check timestamp preservation
        assert sanitized["timestamp"] == data["timestamp"]

    def test_sanitize_for_anonymous_with_user_id(self):
        """Test anonymization with explicit user ID."""
        data = {"author": "John Doe", "content": "Personal message with 555-1234"}

        user_id = "specific_user_456"
        sanitized = sanitize_for_anonymous(data, user_id)

        # User ID should be added and hashed if it was in original data
        # But sanitize_for_anonymous doesn't add user_id if not present
        if "user_id" in sanitized:
            expected_hash = f"anon_{hashlib.sha256(user_id.encode()).hexdigest()[:8]}"
            assert sanitized["user_id"] == expected_hash

        # Content should be sanitized
        assert "555-1234" not in sanitized.get("content", "")

    def test_sanitize_for_anonymous_preserves_safe_data(self):
        """Test that safe data is preserved during anonymization."""
        data = {
            "safe_field": "This is safe content",
            "numbers": [1, 2, 3],
            "boolean": True,
            "nested": {"safe": "also safe"},
        }

        sanitized = sanitize_for_anonymous(data)

        assert sanitized["safe_field"] == data["safe_field"]
        assert sanitized["numbers"] == data["numbers"]
        assert sanitized["boolean"] == data["boolean"]
        assert sanitized["nested"] == data["nested"]

    def test_sanitize_trace_content(self):
        """Test trace content sanitization."""
        trace_content = "Thinking about user@email.com and their request. Phone: 555-0123"

        # For anonymous users (consent_stream = "anonymous")
        sanitized = sanitize_trace_content(trace_content, consent_stream="anonymous")

        # Content should be sanitized
        assert "user@email.com" not in sanitized
        assert "555-0123" not in sanitized
        assert "[email]" in sanitized
        assert "[phone]" in sanitized

    def test_content_hash_verification(self):
        """Test that content hashes can be used for verification."""
        original_content = "This is the original message content"

        data = {"content": original_content}

        sanitized = sanitize_for_anonymous(data)

        # Verify hash was created
        assert "content_hash" in sanitized

        # Verify we can recreate the hash to verify content
        expected_hash = hashlib.sha256(original_content.encode()).hexdigest()
        assert sanitized["content_hash"] == expected_hash

        # Different content should produce different hash
        different_data = {"content": "Different content"}
        different_sanitized = sanitize_for_anonymous(different_data)
        assert different_sanitized["content_hash"] != sanitized["content_hash"]

    def test_empty_data_handling(self):
        """Test handling of empty or None data."""
        # Empty dict
        assert sanitize_for_anonymous({}) == {}

        # None values
        data_with_none = {"field": None, "user_id": "user_123"}
        sanitized = sanitize_for_anonymous(data_with_none)
        assert sanitized["field"] is None
        # Check that user_id is properly anonymized
        expected_hash = f"anon_{hashlib.sha256('user_123'.encode()).hexdigest()[:8]}"
        assert sanitized["user_id"] == expected_hash

    def test_sanitize_audit_trail(self):
        """Test that audit trail sanitization preserves hashes for verification."""
        audit_entry = {
            "event_id": "evt_123",
            "user_id": "user_456",
            "action": "message_sent",
            "content": "User sent: Check my profile at http://mysite.com/profile/john",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        sanitized = sanitize_for_anonymous(audit_entry)

        # User should be anonymized
        assert sanitized["user_id"] != "user_456"
        assert sanitized["user_id"].startswith("anon_")

        # Content should be sanitized but hash preserved
        assert "mysite.com" not in sanitized["content"]
        assert "[url]" in sanitized["content"]
        assert "content_hash" in sanitized

        # Event metadata preserved
        assert sanitized["event_id"] == "evt_123"
        assert sanitized["action"] == "message_sent"
        assert sanitized["timestamp"] == audit_entry["timestamp"]

    def test_batch_sanitization(self):
        """Test sanitizing multiple records efficiently."""
        records = [
            {"user_id": "user_1", "message": "test1@email.com"},
            {"user_id": "user_1", "message": "test2@email.com"},  # Same user
            {"user_id": "user_2", "message": "555-1234"},
        ]

        sanitized_records = [sanitize_for_anonymous(r) for r in records]

        # Same user should have same anonymized ID
        assert sanitized_records[0]["user_id"] == sanitized_records[1]["user_id"]

        # Different user should have different ID
        assert sanitized_records[2]["user_id"] != sanitized_records[0]["user_id"]

        # All PII should be redacted
        for record in sanitized_records:
            assert "@email.com" not in record.get("message", "")
            assert "555-1234" not in record.get("message", "")

    def test_special_characters_in_content(self):
        """Test handling of special characters in content."""
        data = {"content": "Unicode: 你好 Emoji: 😊 Special: <>&\"'", "user_id": "user_abc"}

        sanitized = sanitize_for_anonymous(data)

        # Special characters should be preserved
        assert "你好" in sanitized["content"]
        assert "😊" in sanitized["content"]
        assert "<>&\"'" in sanitized["content"]

        # Hash should handle unicode properly
        assert "content_hash" in sanitized
        assert len(sanitized["content_hash"]) == 64  # SHA256 hex length

    def test_should_sanitize_for_user(self):
        """Test consent stream detection."""
        # Should sanitize for anonymous/expired/revoked
        assert should_sanitize_for_user("anonymous") is True
        assert should_sanitize_for_user("expired") is True
        assert should_sanitize_for_user("revoked") is True
        assert should_sanitize_for_user("ANONYMOUS") is True  # Case insensitive

        # Should not sanitize for others
        assert should_sanitize_for_user("temporary") is False
        assert should_sanitize_for_user("partnered") is False
        assert should_sanitize_for_user(None) is False
        assert should_sanitize_for_user("") is False

    def test_sanitize_correlation_parameters(self):
        """Test correlation parameter sanitization."""
        params = {"user_id": "user_123", "message": "Contact me at test@example.com", "correlation_id": "corr_456"}

        # Without consent stream (no sanitization)
        result = sanitize_correlation_parameters(params)
        assert result == params

        # With anonymous consent (should sanitize)
        result = sanitize_correlation_parameters(params, "anonymous")
        assert result["user_id"].startswith("anon_")
        assert "test@example.com" not in result["message"]
        assert result["correlation_id"] == "corr_456"

    def test_sanitize_audit_details(self):
        """Test audit detail sanitization."""
        details = {"user_id": "user_789", "action": "message_sent", "content": "My phone is 555-1234"}

        # Without consent stream
        result = sanitize_audit_details(details)
        assert result == details

        # With revoked consent
        result = sanitize_audit_details(details, "revoked")
        assert result["user_id"].startswith("anon_")
        assert "555-1234" not in result["content"]
        assert result["action"] == "message_sent"

    def test_verify_content_hash(self):
        """Test content hash verification."""
        content = "This is test content"
        full_hash = hashlib.sha256(content.encode()).hexdigest()

        # Full hash match
        assert verify_content_hash(content, full_hash) is True

        # Partial hash match (first 8 chars)
        assert verify_content_hash(content, full_hash[:8]) is True

        # Partial hash match (first 16 chars)
        assert verify_content_hash(content, full_hash[:16]) is True

        # Wrong hash
        assert verify_content_hash(content, "wronghash") is False

        # Different content
        assert verify_content_hash("Different content", full_hash) is False

    def test_create_refutation_proof(self):
        """Test refutation proof creation."""
        claimed = "User said bad things"
        stored_hash = hashlib.sha256("User said good things".encode()).hexdigest()
        actual = "User said good things"

        # Create proof with actual content
        proof = create_refutation_proof(claimed, stored_hash, actual)

        assert hasattr(proof, "timestamp")
        assert proof.stored_hash == stored_hash
        assert proof.matches_stored is False  # Claimed doesn't match stored
        assert proof.actual_matches_stored is True  # Actual matches stored
        assert proof.claimed_matches_actual is False  # Claimed != actual

        # Create proof without actual content
        proof_no_actual = create_refutation_proof(claimed, stored_hash)
        assert proof_no_actual.actual_content_hash is None
        assert proof_no_actual.matches_stored is False


class TestPrivacyIntegration:
    """Integration tests for privacy functions."""

    def test_anonymous_user_flow(self):
        """Test complete flow for anonymous user data handling."""
        # Simulate user interaction
        user_interaction = {
            "user_id": "discord_user_123456789",
            "channel_id": "channel_987",
            "message": "Hi, email me at user@test.com about the issue",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"platform": "discord", "mentions": ["<@987654321>"]},
        }

        # Sanitize for storage
        sanitized = sanitize_for_anonymous(user_interaction)

        # Verify anonymization
        assert sanitized["user_id"].startswith("anon_")
        assert len(sanitized["user_id"]) == 13

        # Verify PII removal
        assert "user@test.com" not in sanitized["message"]
        assert "[email]" in sanitized["message"]

        # Verify hash for future verification
        assert "message_hash" in sanitized
        original_hash = hashlib.sha256(user_interaction["message"].encode()).hexdigest()
        assert sanitized["message_hash"] == original_hash

        # Metadata is preserved as-is (not recursively sanitized)
        assert sanitized["metadata"] == user_interaction["metadata"]

        # Simulate verification later
        # We can prove the sanitized message came from the original
        claimed_original = "Hi, email me at user@test.com about the issue"
        claimed_hash = hashlib.sha256(claimed_original.encode()).hexdigest()
        assert claimed_hash == sanitized["message_hash"]

    def test_consent_revocation_flow(self):
        """Test data handling when consent is revoked."""
        # User data before revocation
        user_data = {
            "user_id": "partnered_user_999",
            "profile": {"name": "John Doe", "email": "john@example.com", "trust_score": 0.95},
            "messages": ["Check my website https://johndoe.com", "Call me at 555-0199"],
        }

        # On consent revocation, anonymize
        anonymized = sanitize_for_anonymous(user_data)

        # User ID should be hashed
        assert anonymized["user_id"] != "partnered_user_999"
        assert anonymized["user_id"].startswith("anon_")

        # Profile is preserved as-is (nested dicts not recursively sanitized)
        assert anonymized["profile"] == user_data["profile"]

        # Messages list is preserved as-is (lists not recursively sanitized)
        assert anonymized["messages"] == user_data["messages"]
