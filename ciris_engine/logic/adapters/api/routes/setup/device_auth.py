"""Shared constants for the licensed-package download endpoint.

The device auth flow itself (connect-node, connect-node/status,
reset-device-auth) is served natively by the local ciris-server node on
port 4243 — the brain no longer proxies Portal device auth. Only the
Portal host allowlist survives here, used by ``download_package`` for
SSRF protection.
"""

# Trusted Portal domains for SSRF protection
# Only these hosts are allowed for licensed package download
ALLOWED_PORTAL_HOSTS = frozenset(
    {
        "portal.ciris.ai",
        "portal.ciris-services-1.ai",
        "portal.ciris-services-2.ai",
        "localhost",
        "127.0.0.1",
    }
)
