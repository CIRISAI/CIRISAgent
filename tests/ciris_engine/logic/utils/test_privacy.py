import hashlib
from ciris_engine.logic.utils.privacy import (
    should_sanitize_for_user,
    redact_personal_info,
    sanitize_for_anonymous,
    sanitize_correlation_parameters,
    sanitize_audit_details,
    sanitize_trace_content,
    verify_content_hash,
    create_refutation_proof,
    REDACTED_MENTION,
    REDACTED_EMAIL,
    REDACTED_PHONE,
    REDACTED_URL,
    REDACTED_NAME,
)

class TestShouldSanitize:
    def test_should_sanitize_for_anonymous_types(self):
        assert should_sanitize_for_user("anonymous")
        assert should_sanitize_for_user("expired")
        assert should_sanitize_for_user("revoked")
        assert should_sanitize_for_user("Anonymous")

    def test_should_not_sanitize_for_other_types(self):
        assert not should_sanitize_for_user(None)
        assert not should_sanitize_for_user("")
        assert not should_sanitize_for_user("full_consent")
        assert not should_sanitize_for_user("temporary")

class TestRedactPersonalInfo:
    def test_redacts_all_pii_patterns(self):
        text = (
            "Hello <@12345>, please email me at test.user@example.com. "
            "My number is (555) 555-1234. Visit https://example.com. "
            "I'm John Doe."
        )
        # The URL regex is greedy and consumes the trailing period.
        expected = (
            f"Hello {REDACTED_MENTION}, please email me at {REDACTED_EMAIL}. "
            f"My number is {REDACTED_PHONE}. Visit {REDACTED_URL} "
            f"I'm {REDACTED_NAME}."
        )
        assert redact_personal_info(text) == expected

    def test_does_not_change_clean_text(self):
        text = "This is a clean sentence with no PII."
        assert redact_personal_info(text) == text

class TestSanitizeForAnonymous:
    def test_sanitizes_data_dictionary(self):
        data = {
            "author_name": "John Doe",
            "email": "j.doe@example.com",
            "author_id": "user123",
            "content": "This is the original message content.",
            "other_field": "should remain",
        }

        sanitized = sanitize_for_anonymous(data)

        # PII fields are removed
        assert "author_name" not in sanitized
        assert "email" not in sanitized

        # Hashable fields are hashed
        expected_hash = f"anon_{hashlib.sha256(b'user123').hexdigest()[:8]}"
        assert sanitized["author_id"] == expected_hash

        # Content fields are hashed, truncated, and redacted
        assert "content_hash" in sanitized
        assert sanitized["content"] == "This is the original message content." # Not long enough to truncate

        # Other fields are preserved
        assert sanitized["other_field"] == "should remain"

    def test_content_truncation(self):
        long_content = "a" * 60
        data = {"message": long_content}
        sanitized = sanitize_for_anonymous(data)
        assert sanitized["message"] == "a" * 47 + "..."
        assert "message_hash" in sanitized

class TestWrapperFunctions:
    def test_sanitize_wrappers_no_op_on_consent(self):
        params = {"key": "value"}
        assert sanitize_correlation_parameters(params, "full") is params
        assert sanitize_audit_details(params, "full") is params

    def test_sanitize_wrappers_act_on_anonymous(self):
        params = {"author_name": "John", "author_id": "123"}
        sanitized = sanitize_correlation_parameters(params, "anonymous")
        assert "author_name" not in sanitized
        assert "author_id" in sanitized

class TestSanitizeTraceContent:
    def test_no_op_on_consent(self):
        content = "some content"
        assert sanitize_trace_content(content, "full") == content

    def test_sanitizes_for_anonymous(self):
        content = "My email is test@example.com"
        sanitized = sanitize_trace_content(content, "anonymous")

        assert REDACTED_EMAIL in sanitized
        assert "[Hash:" in sanitized

    def test_long_trace_content_truncation(self):
        content = "a" * 600
        sanitized = sanitize_trace_content(content, "anonymous")
        assert len(sanitized) <= 500 + 25 # 500 for content, plus hash
        assert sanitized.startswith("a" * 497 + "...")
        assert "[Hash:" in sanitized

class TestHashingUtils:
    def test_verify_content_hash(self):
        content = "hello world"
        full_hash = hashlib.sha256(content.encode()).hexdigest()
        partial_hash = full_hash[:16]

        assert verify_content_hash(content, full_hash)
        assert verify_content_hash(content, partial_hash)
        assert not verify_content_hash(content, "wrong_hash")
        assert not verify_content_hash("wrong content", full_hash)

    def test_create_refutation_proof(self):
        stored_hash = hashlib.sha256(b"actual").hexdigest()

        # Claim matches
        proof1 = create_refutation_proof("actual", stored_hash)
        assert proof1["matches_stored"]

        # Claim does not match
        proof2 = create_refutation_proof("claimed", stored_hash)
        assert not proof2["matches_stored"]

        # With actual content provided
        proof3 = create_refutation_proof("claimed", stored_hash, "actual")
        assert not proof3["matches_stored"]
        assert proof3["actual_matches_stored"]
        assert not proof3["claimed_matches_actual"]
