"""
Regression tests for CIRISAgent#846 — OAuth redirect_uri must not leak bearer
tokens to attacker-reachable private hosts, while still supporting the Home
Assistant IndieAuth flow (HTTP redirect back to a localhost OAuth endpoint).
"""

from unittest.mock import patch

import pytest

from ciris_engine.logic.adapters.api.routes import auth


@pytest.mark.parametrize(
    "uri",
    [
        "http://127.0.0.1:8123/auth/external/callback",  # HA IndieAuth -> localhost
        "http://localhost:9000/oauth-complete",
        "http://[::1]:8080/cb",
    ],
)
def test_loopback_http_redirect_allowed(uri):
    """#846: loopback (same machine) stays trusted — the HA localhost flow."""
    assert auth.validate_redirect_uri(uri) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "http://192.168.1.50:9999/steal",  # LAN host an attacker can read
        "http://10.0.0.5/cb",
        "http://homeassistant.local/cb",  # .local mDNS is LAN, not loopback
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata / link-local
    ],
)
def test_non_loopback_private_redirect_blocked_by_default(uri):
    """#846: LAN / .local / link-local hosts are NOT trusted by default."""
    with patch.object(auth, "OAUTH_ALLOW_PRIVATE_REDIRECTS", False), patch.object(
        auth, "OAUTH_ALLOWED_REDIRECT_DOMAINS", []
    ), patch.object(auth, "OAUTH_FRONTEND_URL", None):
        assert auth.validate_redirect_uri(uri) is None


def test_opt_in_allows_lan_redirect():
    """OAUTH_ALLOW_PRIVATE_REDIRECTS re-enables LAN redirects for trusted nets."""
    uri = "http://192.168.1.50:8123/cb"
    with patch.object(auth, "OAUTH_ALLOW_PRIVATE_REDIRECTS", True):
        assert auth.validate_redirect_uri(uri) == uri


def test_allowlisted_private_host_allowed():
    """A specific private host on the allowlist is permitted without the flag."""
    uri = "http://homeassistant.local/cb"
    with patch.object(auth, "OAUTH_ALLOW_PRIVATE_REDIRECTS", False), patch.object(
        auth, "OAUTH_ALLOWED_REDIRECT_DOMAINS", ["homeassistant.local"]
    ), patch.object(auth, "OAUTH_FRONTEND_URL", None):
        assert auth.validate_redirect_uri(uri) == uri


def test_relative_paths_and_protocol_relative():
    assert auth.validate_redirect_uri("/dashboard") == "/dashboard"
    assert auth.validate_redirect_uri("//evil.com/x") is None


def test_public_untrusted_domain_blocked():
    with patch.object(auth, "OAUTH_ALLOWED_REDIRECT_DOMAINS", []), patch.object(
        auth, "OAUTH_FRONTEND_URL", None
    ):
        assert auth.validate_redirect_uri("https://evil.example/x") is None
