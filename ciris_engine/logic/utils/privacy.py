"""
Privacy utilities for respecting consent in audit and correlation storage.

Provides functions to sanitize data based on user consent stream.
"""

import hashlib
from typing import Any, Dict, Optional


def sanitize_for_anonymous(data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sanitize data for anonymous users.
    
    Removes PII while preserving necessary audit information.
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
    
    # Truncate content for anonymous users (keep first 50 chars for context)
    content_fields = ["content", "message", "text", "body"]
    for field in content_fields:
        if field in sanitized and sanitized[field]:
            content = str(sanitized[field])
            if len(content) > 50:
                sanitized[field] = f"{content[:47]}..."
            # Also redact any mentions or personal info patterns
            sanitized[field] = redact_personal_info(sanitized[field])
    
    return sanitized


def redact_personal_info(text: str) -> str:
    """
    Redact potential personal information from text.
    
    Replaces mentions, emails, phone numbers, etc.
    """
    import re
    
    # Discord mentions
    text = re.sub(r'<@!?\d+>', '[mention]', text)
    
    # Email addresses
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[email]', text)
    
    # Phone numbers (basic patterns)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[phone]', text)
    text = re.sub(r'\b\d{10,}\b', '[number]', text)
    
    # URLs that might contain personal info
    text = re.sub(r'https?://[^\s]+', '[url]', text)
    
    # Names after "I am" or "My name is"
    text = re.sub(r'(I am|My name is|I\'m)\s+\w+(\s+\w+)?', r'\1 [name]', text, flags=re.IGNORECASE)
    
    return text


def should_sanitize_for_user(user_consent_stream: Optional[str]) -> bool:
    """
    Determine if data should be sanitized based on consent stream.
    
    Returns True for anonymous or expired temporary consent.
    """
    if not user_consent_stream:
        return False
    
    return user_consent_stream.lower() in ["anonymous", "expired", "revoked"]


def sanitize_correlation_parameters(
    parameters: Dict[str, Any],
    consent_stream: Optional[str] = None
) -> Dict[str, Any]:
    """
    Sanitize correlation parameters based on consent.
    
    Used when storing ServiceRequestData parameters.
    """
    if not should_sanitize_for_user(consent_stream):
        return parameters
    
    return sanitize_for_anonymous(parameters)


def sanitize_audit_details(
    details: Dict[str, Any],
    consent_stream: Optional[str] = None  
) -> Dict[str, Any]:
    """
    Sanitize audit entry details based on consent.
    
    Used when creating audit entries.
    """
    if not should_sanitize_for_user(consent_stream):
        return details
    
    return sanitize_for_anonymous(details)


def sanitize_thought_content(
    content: str,
    consent_stream: Optional[str] = None
) -> str:
    """
    Sanitize thought content based on consent.
    
    Preserves semantic meaning while removing PII.
    """
    if not should_sanitize_for_user(consent_stream):
        return content
    
    # For anonymous users, redact personal info but keep semantic content
    sanitized = redact_personal_info(content)
    
    # If content is very long, truncate to reasonable length
    if len(sanitized) > 500:
        sanitized = f"{sanitized[:497]}..."
    
    return sanitized