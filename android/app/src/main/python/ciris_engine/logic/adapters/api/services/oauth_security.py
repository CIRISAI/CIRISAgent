"""OAuth security utilities for profile picture validation."""

from typing import Optional
from urllib.parse import urlparse

# Domain whitelist for OAuth profile pictures
ALLOWED_AVATAR_DOMAINS = frozenset(
    [
        "lh3.googleusercontent.com",  # Google
        "cdn.discordapp.com",  # Discord
        "avatars.githubusercontent.com",  # GitHub
        "secure.gravatar.com",  # Gravatar
        "www.gravatar.com",  # Gravatar (www)
    ]
)


def validate_oauth_picture_url(url: Optional[str]) -> bool:
    """
    Validate OAuth profile picture URL for security.

    Ensures:
    - URL uses HTTPS protocol
    - Domain is in the allowed whitelist
    - No path traversal attempts
    - Reasonable URL length

    Args:
        url: Profile picture URL from OAuth provider

    Returns:
        True if URL is safe, False otherwise
    """
    if not url:
        return True  # Empty is safe

    # Basic validation - strip whitespace
    url = url.strip()

    try:
        parsed = urlparse(url)

        # Only allow HTTPS
        if parsed.scheme.lower() != "https":
            return False

        # Check domain whitelist (case-insensitive)
        if parsed.netloc.lower() not in ALLOWED_AVATAR_DOMAINS:
            return False

        # Validate path doesn't contain traversal attempts
        if ".." in parsed.path or "//" in parsed.path:
            return False

        # Check for script injection in query or fragment
        dangerous_patterns = ["<script", "<img", "javascript:", "vbscript:"]
        url_lower = url.lower()
        for pattern in dangerous_patterns:
            if pattern in url_lower:
                return False

        # Ensure URL length is reasonable (2000 chars = browser limit)
        if len(url) > 2000:
            return False

        return True
    except Exception:
        return False
