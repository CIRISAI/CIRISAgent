"""
Privacy utilities for respecting consent in audit and correlation storage.

Provides functions to sanitize data based on user consent stream.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.schemas.audit.verification import RefutationProof
from ciris_engine.schemas.types import JSONDict

# Redaction placeholders - constants to avoid duplication
REDACTED_MENTION = "[mention]"
REDACTED_EMAIL = "[email]"
REDACTED_PHONE = "[phone]"
REDACTED_NUMBER = "[number]"
REDACTED_URL = "[url]"
REDACTED_NAME = "[name]"


def sanitize_for_anonymous(data: JSONDict, user_id: Optional[str] = None) -> JSONDict:
    """
    Sanitize data for anonymous users.

    Removes PII while preserving necessary audit information.
    Stores content hash for future verification/refutation.

    Args:
        data: Data to sanitize (JSON-compatible dict)
        user_id: Optional user ID for context

    Returns:
        Sanitized data with PII removed/hashed
    """
    sanitized = data.copy()

    # Fields to completely remove for anonymous users
    pii_fields = [
        "author_name",
        "username",
        "display_name",
        "real_name",
        "email",
        "phone",
        "address",
        "ip_address",
    ]

    for field in pii_fields:
        if field in sanitized:
            del sanitized[field]

    # Fields to hash instead of storing raw
    hashable_fields = [
        "author_id",
        "user_id",
        "discord_id",
        "member_id",
    ]

    for field in hashable_fields:
        if field in sanitized and sanitized[field]:
            # Replace with hash
            value = str(sanitized[field])
            sanitized[field] = f"anon_{hashlib.sha256(value.encode()).hexdigest()[:8]}"

    # Handle content fields - hash original, store sanitized
    content_fields = ["content", "message", "text", "body"]
    for field in content_fields:
        if field in sanitized and sanitized[field]:
            original_content = str(sanitized[field])

            # Create hash of original content for verification
            content_hash = hashlib.sha256(original_content.encode()).hexdigest()
            sanitized[f"{field}_hash"] = content_hash

            # Store truncated/redacted version
            if len(original_content) > 50:
                sanitized[field] = f"{original_content[:47]}..."
            else:
                sanitized[field] = original_content

            # Redact any mentions or personal info patterns - get as string first
            field_value = get_str(sanitized, field, "")
            sanitized[field] = redact_personal_info(field_value)

    return sanitized


def redact_personal_info(text: str) -> str:
    """
    Redact potential personal information from text.

    Replaces mentions, emails, phone numbers, etc.
    """
    import re

    # Discord mentions - simple and clear
    text = re.sub(r"<@!?\d+>", REDACTED_MENTION, text)

    # Email addresses - simplified to avoid backtracking DoS
    # Limit length and use word boundaries to prevent ReDoS
    text = re.sub(
        r"\b[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}@[a-zA-Z0-9][a-zA-Z0-9.-]{0,62}\.[a-zA-Z]{2,6}\b", REDACTED_EMAIL, text
    )

    # Phone numbers - handle multiple formats robustly
    # Format: (555) 555-1234 or (555)555-1234
    text = re.sub(r"\(\d{3}\)\s*\d{3}[-.]?\d{4}", REDACTED_PHONE, text)
    # Format: 555-555-1234 or 555.555.1234 or 555 555 1234
    text = re.sub(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", REDACTED_PHONE, text)
    # Format: 5555551234 (10 digits together)
    text = re.sub(r"\b\d{10}\b", REDACTED_PHONE, text)
    # Format: 555-1234 (7 digit local)
    text = re.sub(r"\b\d{3}-\d{4}\b", REDACTED_PHONE, text)
    # Any other long number sequence (11+ digits)
    text = re.sub(r"\b\d{11,}\b", REDACTED_NUMBER, text)

    # URLs - simple pattern
    text = re.sub(r"https?://[^\s]+", REDACTED_URL, text)

    # Names after common phrases - keep it simple
    text = re.sub(r"(I am|My name is|I\'m)\s+\w+(\s+\w+)?", rf"\1 {REDACTED_NAME}", text, flags=re.IGNORECASE)

    return text


def should_sanitize_for_user(user_consent_stream: Optional[str]) -> bool:
    """
    Determine if data should be sanitized based on consent stream.

    Returns True for anonymous or expired temporary consent.
    """
    if not user_consent_stream:
        return False

    return user_consent_stream.lower() in ["anonymous", "expired", "revoked"]


def sanitize_correlation_parameters(parameters: JSONDict, consent_stream: Optional[str] = None) -> JSONDict:
    """
    Sanitize correlation parameters based on consent.

    Used when storing ServiceRequestData parameters.

    Args:
        parameters: Correlation parameters to sanitize
        consent_stream: User consent stream status

    Returns:
        Sanitized parameters if consent requires it, otherwise original
    """
    if not should_sanitize_for_user(consent_stream):
        return parameters

    return sanitize_for_anonymous(parameters)


def sanitize_audit_details(details: JSONDict, consent_stream: Optional[str] = None) -> JSONDict:
    """
    Sanitize audit entry details based on consent.

    Used when creating audit entries.

    Args:
        details: Audit entry details to sanitize
        consent_stream: User consent stream status

    Returns:
        Sanitized details if consent requires it, otherwise original
    """
    if not should_sanitize_for_user(consent_stream):
        return details

    return sanitize_for_anonymous(details)


def sanitize_trace_content(content: str, consent_stream: Optional[str] = None) -> str:
    """
    Sanitize trace/audit content based on consent.

    Preserves semantic meaning while removing PII.
    Returns sanitized content with hash appended for verification.

    Note: This is for audit trails and traces only.
    Thoughts themselves are never sanitized.
    """
    if not should_sanitize_for_user(consent_stream):
        return content

    # Hash the original content for future verification
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    # For anonymous users, redact personal info but keep semantic content
    sanitized = redact_personal_info(content)

    # If content is very long, truncate to reasonable length
    if len(sanitized) > 500:
        sanitized = f"{sanitized[:497]}..."

    # Append hash for verification/refutation capability
    sanitized += f" [Hash: {content_hash[:16]}]"

    return sanitized


def verify_content_hash(content: str, claimed_hash: str) -> bool:
    """
    Verify if content matches a claimed hash.

    Used for refutation - proving we did/didn't see specific content.

    Args:
        content: The content to verify
        claimed_hash: The hash to check against

    Returns:
        True if content matches the hash
    """
    actual_hash = hashlib.sha256(content.encode()).hexdigest()

    # Support partial hash matching (first 8-16 chars often stored)
    if len(claimed_hash) < len(actual_hash):
        return actual_hash.startswith(claimed_hash)

    return actual_hash == claimed_hash


def create_refutation_proof(
    claimed_content: str, stored_hash: str, actual_content: Optional[str] = None
) -> RefutationProof:
    """
    Create a refutation proof for disputed content.

    Args:
        claimed_content: What someone claims was said
        stored_hash: The hash we have stored
        actual_content: The actual content if available

    Returns:
        Proof dictionary with verification results
    """
    claimed_content_hash = hashlib.sha256(claimed_content.encode()).hexdigest()
    matches_stored = verify_content_hash(claimed_content, stored_hash)

    actual_content_hash = None
    actual_matches_stored = None
    claimed_matches_actual = None

    if actual_content:
        actual_content_hash = hashlib.sha256(actual_content.encode()).hexdigest()
        actual_matches_stored = verify_content_hash(actual_content, stored_hash)
        claimed_matches_actual = claimed_content_hash == actual_content_hash

    return RefutationProof(
        timestamp=datetime.now(timezone.utc).isoformat(),
        stored_hash=stored_hash,
        claimed_content_hash=claimed_content_hash,
        matches_stored=matches_stored,
        actual_content_hash=actual_content_hash,
        actual_matches_stored=actual_matches_stored,
        claimed_matches_actual=claimed_matches_actual,
    )
