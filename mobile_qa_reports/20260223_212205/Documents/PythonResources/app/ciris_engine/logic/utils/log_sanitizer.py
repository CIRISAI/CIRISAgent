"""
Log sanitization utilities to prevent log injection attacks.

This module provides functions to sanitize user-controlled data before logging,
preventing log injection vulnerabilities identified by SonarCloud.
"""

import re
from typing import Optional


def sanitize_for_log(text: Optional[str], max_length: int = 100) -> str:
    """
    Sanitize text for safe logging by removing control characters.

    This function prevents log injection attacks by:
    1. Removing control characters and non-printable characters
    2. Replacing newlines, returns, and tabs with spaces
    3. Truncating to a reasonable length
    4. Using an allowlist approach for permitted characters

    Args:
        text: The text to sanitize (may be user-controlled)
        max_length: Maximum length of the output string

    Returns:
        Sanitized string safe for logging
    """
    if not text:
        return "N/A"

    # Convert to string if not already
    text = str(text)

    # Remove all non-printable and control characters
    # Only allow alphanumeric, spaces, and basic safe punctuation
    sanitized = re.sub(r"[^\w\s\-_.,/@:()]", "?", text)

    # Remove any remaining newlines, returns, tabs (redundant but explicit)
    sanitized = sanitized.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Collapse multiple spaces into single space
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # Truncate to reasonable length
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3] + "..."

    return sanitized


def sanitize_email(email: Optional[str]) -> str:
    """
    Sanitize email address for logging.

    Args:
        email: Email address to sanitize

    Returns:
        Sanitized email safe for logging
    """
    if not email:
        return "N/A"

    # Basic email sanitization - preserve format but remove control chars
    sanitized = re.sub(r"[^\w\s\-_.@]", "?", str(email))
    sanitized = sanitized.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + "..."

    return sanitized


def sanitize_username(username: Optional[str]) -> str:
    """
    Sanitize username for logging.

    Args:
        username: Username to sanitize

    Returns:
        Sanitized username safe for logging
    """
    if not username:
        return "N/A"

    # Usernames should only contain alphanumeric and basic chars
    sanitized = re.sub(r"[^\w\s\-_.]", "?", str(username))
    sanitized = sanitized.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Limit length
    if len(sanitized) > 50:
        sanitized = sanitized[:47] + "..."

    return sanitized
