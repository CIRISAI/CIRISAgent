"""
CIRISNode ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for connecting existing agents to CIRISNode:
1. Discovery - Select CIRISNode region (US, EU, or custom)
2. Device Auth - RFC 8628 device authorization with CIRISPortal
3. Confirm - Review provisioned configuration and apply

This flow is for EXISTING agents that want to connect to CIRISNode.
For first-run setup, use /v1/setup/connect-node instead.

Key difference from first-run:
- Existing agent has identity (agent_id, possibly existing signing key)
- agent_info includes agent's hash and public key
- Portal may recognize the agent if previously registered
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Available CIRISNode regions
CIRISNODE_REGIONS = [
    {
        "id": "us-primary",
        "label": "CIRIS US (Primary)",
        "description": "Primary CIRISNode in United States",
        "metadata": {
            "portal_url": "https://portal.ciris-services-1.ai",
            "node_url": "https://node.ciris-services-1.ai",
            "region": "us-east",
        },
    },
    {
        "id": "eu",
        "label": "CIRIS EU",
        "description": "CIRISNode in European Union",
        "metadata": {
            "portal_url": "https://portal.ciris-services-2.ai",
            "node_url": "https://node.ciris-services-2.ai",
            "region": "eu-west",
        },
    },
]


class CIRISNodeConfigurableAdapter:
    """CIRISNode configurable adapter with RFC 8628 device auth support.

    Implements ConfigurableAdapterProtocol for connecting existing agents
    to CIRISNode using the device authorization flow.

    Device Auth Flow (RFC 8628):
    1. Agent requests device code from Portal
    2. Portal returns device_code, user_code, verification_uri
    3. User visits verification_uri and enters user_code
    4. Agent polls Portal until authorized
    5. Portal returns signing key and provisioned template

    Usage via API:
        1. POST /v1/system/adapters/cirisnode/configure/start
        2. POST /v1/system/adapters/configure/{session_id}/step (discovery)
        3. POST /v1/system/adapters/configure/{session_id}/step (device_auth)
        4. Poll: POST /v1/system/adapters/configure/{session_id}/step (poll=true)
        5. POST /v1/system/adapters/configure/{session_id}/complete
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        signing_key_b64: Optional[str] = None,
    ) -> None:
        """Initialize the CIRISNode configurable adapter.

        Args:
            config: Optional existing configuration
            agent_id: Current agent's ID (for agent_info)
            signing_key_b64: Current agent's signing key if any (base64 encoded)
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None
        self._agent_id = agent_id
        self._signing_key_b64 = signing_key_b64

        # Device auth state
        self._device_code: Optional[str] = None
        self._user_code: Optional[str] = None
        self._portal_url: Optional[str] = None

        logger.info("CIRISNodeConfigurableAdapter initialized")

    def set_agent_identity(self, agent_id: str, signing_key_b64: Optional[str] = None) -> None:
        """Set the agent's identity for device auth.

        Args:
            agent_id: Agent's ID
            signing_key_b64: Agent's signing key (base64 encoded) if any
        """
        self._agent_id = agent_id
        self._signing_key_b64 = signing_key_b64

    def _get_agent_info(self) -> Dict[str, Any]:
        """Get agent info to send with device auth request.

        For existing agents, includes:
        - agent_id_hash: SHA-256 hash of agent_id (first 16 chars)
        - has_signing_key: Whether agent has an existing signing key
        - public_key_fingerprint: SHA-256 of public key if available

        Returns:
            Agent info dict
        """
        agent_info: Dict[str, Any] = {}

        if self._agent_id:
            # Send hash, not raw agent_id
            agent_hash = hashlib.sha256(self._agent_id.encode()).hexdigest()[:16]
            agent_info["agent_id_hash"] = agent_hash

        if self._signing_key_b64:
            agent_info["has_signing_key"] = True
            # Could compute public key fingerprint here if needed

        return agent_info

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Discover available CIRISNode regions.

        Args:
            discovery_type: Type of discovery ("regions", "manual", etc.)

        Returns:
            List of available CIRISNode regions
        """
        logger.info(f"Running CIRISNode discovery: {discovery_type}")

        if discovery_type in ("regions", "default"):
            return CIRISNODE_REGIONS
        elif discovery_type == "manual":
            return []  # User enters custom URL

        return CIRISNODE_REGIONS

    async def get_oauth_url(
        self,
        base_url: str,
        state: str,
        code_challenge: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate device authorization with CIRISPortal.

        For device auth, this returns a dict with device code info
        instead of a URL string.

        Args:
            base_url: Portal URL (e.g., https://portal.ciris-services-1.ai)
            state: Session ID for tracking
            code_challenge: Unused (device auth doesn't use PKCE)
            callback_base_url: Unused
            redirect_uri: Unused
            platform: Unused

        Returns:
            Dict with device_code, user_code, verification_uri_complete, etc.
        """
        self._portal_url = base_url.rstrip("/")
        device_auth_endpoint = "/api/device/authorize"

        agent_info = self._get_agent_info()
        logger.info(f"[DEVICE AUTH] Initiating with portal: {self._portal_url}")
        logger.info(f"[DEVICE AUTH] Agent info: {agent_info}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{self._portal_url}{device_auth_endpoint}",
                    json={
                        "portal_url": self._portal_url,
                        "agent_info": agent_info,
                    },
                )
                response.raise_for_status()
                data = response.json()

                self._device_code = data.get("device_code")
                self._user_code = data.get("user_code")

                logger.info(f"[DEVICE AUTH] Got user code: {self._user_code}")
                return {
                    "device_code": data.get("device_code"),
                    "user_code": data.get("user_code"),
                    "verification_uri_complete": data.get("verification_uri_complete"),
                    "expires_in": data.get("expires_in", 900),
                    "interval": data.get("interval", 5),
                    "portal_url": self._portal_url,
                }

        except httpx.HTTPError as e:
            logger.error(f"[DEVICE AUTH] Failed to initiate: {e}")
            raise RuntimeError(f"Failed to initiate device auth: {e}")

    async def handle_oauth_callback(
        self,
        code: str,
        state: str,
        base_url: str,
        code_verifier: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Poll for device authorization completion.

        For device auth, 'code' is actually the device_code.

        Args:
            code: Device code from initiation
            state: Session ID
            base_url: Portal URL
            code_verifier: Unused
            callback_base_url: Unused
            redirect_uri: Unused
            platform: Unused

        Returns:
            Dict with status and result data
        """
        portal_url = base_url.rstrip("/") if base_url else self._portal_url
        device_token_endpoint = "/api/device/token"

        logger.info(f"[DEVICE AUTH] Polling for completion, device_code: {code[:8]}...")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    f"{portal_url}{device_token_endpoint}",
                    json={"device_code": code},
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "pending")

                    if status == "complete":
                        logger.info("[DEVICE AUTH] Authorization complete!")
                        return {
                            "status": "complete",
                            "provisioned_template": data.get("provisioned_template"),
                            "approved_adapters": data.get("approved_adapters", []),
                            "signing_key_b64": data.get("signing_key_b64"),
                            "key_id": data.get("key_id"),
                            "org_id": data.get("org_id"),
                            "stewardship_tier": data.get("stewardship_tier"),
                            "node_url": data.get("node_url"),
                        }
                    elif status == "pending":
                        return {"status": "pending"}
                    else:
                        return {
                            "status": "error",
                            "error": data.get("error", "Unknown error"),
                        }

                elif response.status_code == 400:
                    # Authorization pending or slow down
                    data = response.json()
                    error = data.get("error", "")
                    if error == "authorization_pending":
                        return {"status": "pending"}
                    elif error == "slow_down":
                        return {"status": "pending", "slow_down": True}
                    else:
                        return {"status": "error", "error": error}
                else:
                    return {
                        "status": "error",
                        "error": f"HTTP {response.status_code}",
                    }

        except httpx.HTTPError as e:
            logger.error(f"[DEVICE AUTH] Poll error: {e}")
            return {"status": "error", "error": str(e)}

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_region":
            return CIRISNODE_REGIONS

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate CIRISNode configuration before applying.

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating CIRISNode configuration")

        if not config:
            return False, "Configuration is empty"

        # Check for device auth result
        device_auth_result = config.get("device_auth_result", {})
        if not device_auth_result:
            return False, "Device authorization not completed"

        # Check for signing key
        if not device_auth_result.get("signing_key_b64"):
            return False, "No signing key provisioned"

        # Check for node URL
        node_url = device_auth_result.get("node_url")
        if not node_url:
            return False, "No CIRISNode URL provisioned"

        # Optionally test connectivity to CIRISNode
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{node_url}/health")
                if response.status_code != 200:
                    return False, f"CIRISNode health check failed: HTTP {response.status_code}"
        except httpx.HTTPError as e:
            logger.warning(f"CIRISNode connectivity check failed (non-fatal): {e}")
            # Don't fail validation on connectivity - node might be temporarily unavailable

        logger.info("CIRISNode configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores signing key and configures CIRISNode adapter.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying CIRISNode configuration")

        device_auth_result = config.get("device_auth_result", {})

        # Save signing key
        signing_key_b64 = device_auth_result.get("signing_key_b64")
        if signing_key_b64:
            try:
                from ciris_engine.logic.audit.signing_protocol import UnifiedSigningKey
                from ciris_engine.logic.utils.path_resolution import get_data_dir

                save_path = get_data_dir() / "agent_signing.key"
                save_path.parent.mkdir(parents=True, exist_ok=True)

                # Decode and save
                import base64

                key_bytes = base64.b64decode(signing_key_b64)
                unified_key = UnifiedSigningKey.from_private_bytes(key_bytes)
                unified_key.save(save_path)
                logger.info(f"Saved signing key to {save_path}")
            except Exception as e:
                logger.error(f"Failed to save signing key: {e}")
                return False

        self._applied_config = config.copy()

        # Log sanitized config
        safe_config = {
            "node_url": device_auth_result.get("node_url"),
            "org_id": device_auth_result.get("org_id"),
            "provisioned_template": device_auth_result.get("provisioned_template"),
            "stewardship_tier": device_auth_result.get("stewardship_tier"),
        }
        logger.info(f"CIRISNode configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
