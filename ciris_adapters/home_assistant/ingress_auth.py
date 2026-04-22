"""Home Assistant Ingress Authentication Provider.

When CIRIS runs as a Home Assistant addon, the HA Supervisor acts as a
reverse proxy and injects authentication headers for authenticated users.

This provider extracts user identity from those headers, enabling seamless
authentication without requiring a separate CIRIS login.

Headers injected by HA Supervisor:
- X-Remote-User-Id: HA user's unique identifier
- X-Remote-User-Name: HA user's username (optional)
- X-Remote-User-Display-Name: HA user's display name (optional)

Security:
- Only trust headers from the HA Supervisor (172.30.32.2)
- SUPERVISOR_TOKEN must be present (confirms addon environment)
- Headers cannot be spoofed by external requests

References:
- HA Addon Development: https://developers.home-assistant.io/docs/add-ons/presentation
- Security: "Only connections from 172.30.32.2 must be allowed"
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from fastapi import Request

from ciris_engine.protocols.services.infrastructure.ingress_auth import IngressAuthProviderProtocol, IngressUser
from ciris_engine.schemas.api.auth import UserRole

logger = logging.getLogger(__name__)

# HA Supervisor ingress headers
HA_REMOTE_USER_ID = "X-Remote-User-Id"
HA_REMOTE_USER_NAME = "X-Remote-User-Name"
HA_REMOTE_USER_DISPLAY_NAME = "X-Remote-User-Display-Name"
HA_INGRESS_PATH = "X-Ingress-Path"

# Trusted IP addresses for HA Supervisor
# Per HA docs: "Only connections from 172.30.32.2 must be allowed"
HA_SUPERVISOR_IPS: Set[str] = {
    "172.30.32.2",  # HA Supervisor ingress gateway
    "127.0.0.1",  # Localhost (for testing/development)
    "::1",  # IPv6 localhost
}


class HAIngressAuthProvider(IngressAuthProviderProtocol):
    """Provides authentication via Home Assistant Supervisor ingress.

    When running as an HA addon, the Supervisor:
    1. Authenticates users via HA's auth system
    2. Proxies requests to the addon
    3. Injects X-Remote-User-* headers with authenticated user info

    This provider trusts those headers to identify the user.

    Security considerations:
    - Only enabled when SUPERVISOR_TOKEN is present (confirms addon mode)
    - Only trusts requests from HA Supervisor IP (172.30.32.2)
    - Headers are injected by Supervisor, not user-controllable
    - First authenticated user becomes admin (HA instance owner)
    """

    def __init__(self, *, trust_all_ips: bool = False) -> None:
        """Initialize the HA ingress auth provider.

        Args:
            trust_all_ips: If True, skip IP verification (for testing only!)
        """
        self._supervisor_mode = bool(os.getenv("SUPERVISOR_TOKEN"))
        self._trust_all_ips = trust_all_ips
        # NOTE: _first_user_created flag was REMOVED - it reset on restart and could
        # be consumed by non-user-creating requests. The authoritative first-user
        # check is done in auth.py via database query (len(existing_users) == 0).

        if self._supervisor_mode:
            logger.info("[HA_INGRESS_AUTH] Supervisor mode detected - ingress auth enabled")
            if trust_all_ips:
                logger.warning("[HA_INGRESS_AUTH] ⚠️ IP verification DISABLED - testing mode only!")

    def _is_trusted_ip(self, request: Request) -> bool:
        """Check if request comes from a trusted IP (HA Supervisor).

        Security: Only trust ingress headers from the HA Supervisor gateway.
        This prevents header spoofing from external sources.
        """
        if self._trust_all_ips:
            return True

        client_ip = None

        # Get client IP - FastAPI provides this via request.client
        if request.client:
            client_ip = request.client.host

        # Also check X-Forwarded-For if behind another proxy
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (closest to client)
            first_ip = forwarded_for.split(",")[0].strip()
            # But for our case, we want the immediate upstream (Supervisor)
            # which should be in client.host
            logger.debug(f"[HA_INGRESS_AUTH] X-Forwarded-For: {forwarded_for}")

        if not client_ip:
            logger.warning("[HA_INGRESS_AUTH] No client IP available - rejecting request")
            return False

        # Check against trusted IPs - ONLY exact matches allowed
        # SECURITY: Per HA docs, only 172.30.32.2 (Supervisor) should be trusted
        # The /23 network check was removed as it's too permissive
        if client_ip in HA_SUPERVISOR_IPS:
            logger.debug(f"[HA_INGRESS_AUTH] Trusted IP: {client_ip}")
            return True

        logger.warning(f"[HA_INGRESS_AUTH] Untrusted IP rejected: {client_ip}")
        return False

    @property
    def provider_name(self) -> str:
        """Unique identifier for this auth provider."""
        return "home_assistant"

    def can_handle_request(self, request: Request) -> bool:
        """Check if this request has HA ingress headers from trusted source.

        Only handles requests when:
        1. Running in supervisor mode (SUPERVISOR_TOKEN present)
        2. Request comes from trusted IP (HA Supervisor: 172.30.32.2)
        3. Request has X-Remote-User-Id header (user is authenticated in HA)
        """
        if not self._supervisor_mode:
            return False

        # Security: Verify request comes from HA Supervisor
        if not self._is_trusted_ip(request):
            return False

        user_id = request.headers.get(HA_REMOTE_USER_ID)
        if user_id:
            logger.debug(f"[HA_INGRESS_AUTH] Can handle request - user_id present: {user_id[:8]}...")
            return True

        return False

    async def authenticate_request(self, request: Request) -> Optional[IngressUser]:
        """Extract user information from HA Supervisor headers.

        Args:
            request: FastAPI request with HA ingress headers

        Returns:
            IngressUser with HA user info, or None if headers missing
        """
        user_id = request.headers.get(HA_REMOTE_USER_ID)
        if not user_id:
            logger.warning("[HA_INGRESS_AUTH] Missing X-Remote-User-Id header")
            return None

        username = request.headers.get(HA_REMOTE_USER_NAME)
        display_name = request.headers.get(HA_REMOTE_USER_DISPLAY_NAME)
        ingress_path = request.headers.get(HA_INGRESS_PATH)

        # NOTE: suggested_role is intentionally None here. The first-user check
        # is done authoritatively in auth.py via database query (checking if
        # len(existing_users) == 0). This prevents privilege escalation via
        # restart attacks and race conditions with non-user-creating requests.

        ingress_user = IngressUser(
            external_id=user_id,
            provider=self.provider_name,
            username=username,
            display_name=display_name or username,
            email=None,  # HA doesn't provide email in ingress headers
            suggested_role=None,  # First-user role determined by DB check in auth.py
            metadata={
                "ingress_path": ingress_path,
                "ha_user_id": user_id,
            },
            authenticated_at=datetime.now(timezone.utc),
        )

        logger.info(
            f"[HA_INGRESS_AUTH] Authenticated user: {display_name or username or user_id[:8]}... "
            f"(id: {user_id[:8]}...)"
        )

        return ingress_user

    def is_first_user_admin(self) -> bool:
        """First HA user should be admin (they own the HA instance)."""
        return True

    def skip_setup_wizard_user_step(self) -> bool:
        """Skip user creation - auth handled by HA."""
        return self._supervisor_mode

    def get_provider_metadata(self) -> Dict[str, Any]:
        """Get metadata about this auth provider."""
        return {
            "name": "Home Assistant",
            "description": "Authenticated via Home Assistant",
            "icon": "mdi:home-assistant",
            "trusted_headers": [
                HA_REMOTE_USER_ID,
                HA_REMOTE_USER_NAME,
                HA_REMOTE_USER_DISPLAY_NAME,
            ],
            "supervisor_mode": self._supervisor_mode,
        }


# Singleton instance for the adapter to provide
_ingress_auth_provider: Optional[HAIngressAuthProvider] = None


def get_ha_ingress_auth_provider() -> Optional[HAIngressAuthProvider]:
    """Get the HA ingress auth provider (singleton).

    Returns:
        HAIngressAuthProvider if in supervisor mode, None otherwise.
    """
    global _ingress_auth_provider

    if _ingress_auth_provider is None:
        if os.getenv("SUPERVISOR_TOKEN"):
            _ingress_auth_provider = HAIngressAuthProvider()

    return _ingress_auth_provider
