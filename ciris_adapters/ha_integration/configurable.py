"""
Home Assistant ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for Home Assistant integration:
1. Discovery - Find HA instances via mDNS/Zeroconf
2. OAuth - Authenticate via Home Assistant's IndieAuth-style OAuth2
3. Select - Choose which features to enable
4. Confirm - Review and apply configuration

Home Assistant OAuth2 (per https://developers.home-assistant.io/docs/auth_api/):
- Authorization endpoint: /auth/authorize
- Token endpoint: /auth/token
- Client ID: IndieAuth-style (your application's website URL)
- No pre-registration required
- Access tokens valid 1800 seconds, refresh tokens available

SAFE DOMAIN: Home automation only. Medical/health capabilities are prohibited.
"""

import asyncio
import base64
import hashlib
import logging
import os
import secrets
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import aiohttp

logger = logging.getLogger(__name__)

# Optional mDNS discovery support
try:
    from zeroconf import ServiceBrowser, Zeroconf

    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    logger.info("Zeroconf not available - mDNS discovery disabled")


class HADiscoveryListener:
    """Zeroconf listener for Home Assistant instances."""

    def __init__(self) -> None:
        self.services: List[Dict[str, Any]] = []

    def add_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle discovered service."""
        info = zc.get_service_info(type_, name)
        if info:
            addresses = info.parsed_addresses()
            port = info.port
            if addresses:
                self.services.append(
                    {
                        "id": f"ha_{addresses[0]}_{port}",
                        "label": f"Home Assistant ({addresses[0]}:{port})",
                        "description": name.replace("._home-assistant._tcp.local.", ""),
                        "metadata": {
                            "host": addresses[0],
                            "port": port,
                            "name": name,
                            "url": f"http://{addresses[0]}:{port}",
                        },
                    }
                )

    def remove_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle removed service."""
        pass

    def update_service(self, zc: Any, type_: str, name: str) -> None:
        """Handle updated service."""
        pass


class HAConfigurableAdapter:
    """Home Assistant configurable adapter with OAuth2 support.

    Implements ConfigurableAdapterProtocol for Home Assistant using the
    IndieAuth-style OAuth2 flow documented at:
    https://developers.home-assistant.io/docs/auth_api/

    OAuth2 Flow:
    1. User navigates to HA's /auth/authorize with client_id (our app URL)
    2. User logs in and authorizes the application
    3. HA redirects to redirect_uri with authorization code
    4. We exchange code for access_token + refresh_token at /auth/token
    5. Access token used for API calls (valid 1800 seconds)

    Usage via API:
        1. POST /adapters/ha_integration/configure/start
        2. POST /adapters/configure/{session_id}/step (discovery)
        3. POST /adapters/configure/{session_id}/step (oauth - returns auth URL)
        4. GET /adapters/configure/{session_id}/oauth/callback (handle redirect)
        5. POST /adapters/configure/{session_id}/step (select features)
        6. POST /adapters/configure/{session_id}/complete
    """

    # Home Assistant mDNS service type
    HA_SERVICE_TYPE = "_home-assistant._tcp.local."

    # OAuth2 endpoints (relative to HA instance URL)
    OAUTH_AUTHORIZE_PATH = "/auth/authorize"
    OAUTH_TOKEN_PATH = "/auth/token"

    # CIRIS client ID - used as IndieAuth client identifier
    # This should be the URL of your CIRIS deployment
    DEFAULT_CLIENT_ID = "https://agents.ciris.ai"

    # Available features that can be enabled
    AVAILABLE_FEATURES = {
        "device_control": {
            "label": "Device Control",
            "description": "Control lights, switches, and other devices",
            "default": True,
        },
        "automation_trigger": {
            "label": "Automation Triggers",
            "description": "Trigger Home Assistant automations",
            "default": True,
        },
        "sensor_data": {
            "label": "Sensor Data",
            "description": "Read sensor values and entity states",
            "default": True,
        },
        "event_detection": {
            "label": "Event Detection",
            "description": "Monitor camera events and motion detection",
            "default": False,
        },
        "camera_frames": {
            "label": "Camera Frames",
            "description": "Extract frames from camera streams",
            "default": False,
        },
        "notifications": {
            "label": "Notifications",
            "description": "Send notifications via Home Assistant",
            "default": True,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the HA configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None
        self._discovered_instances: List[Dict[str, Any]] = []

        # PKCE challenge storage (state -> code_verifier)
        self._pkce_verifiers: Dict[str, str] = {}

        # Get client_id from env or use default
        self._client_id = os.getenv("CIRIS_OAUTH_CLIENT_ID", self.DEFAULT_CLIENT_ID)

        logger.info("HAConfigurableAdapter initialized")

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Discover Home Assistant instances.

        Supports:
        - "mdns" / "zeroconf": Use mDNS/Zeroconf discovery
        - "manual": Return empty list (user enters URL manually)
        - "env": Check environment variables

        Args:
            discovery_type: Type of discovery to perform

        Returns:
            List of discovered HA instances
        """
        logger.info(f"Running HA discovery: {discovery_type}")

        if discovery_type in ("mdns", "zeroconf"):
            return await self._discover_mdns()
        elif discovery_type == "env":
            return self._discover_from_env()
        elif discovery_type == "manual":
            return []

        # Default: try mDNS first, then env
        instances = await self._discover_mdns()
        if not instances:
            instances = self._discover_from_env()
        return instances

    async def _discover_mdns(self) -> List[Dict[str, Any]]:
        """Discover HA instances via mDNS/Zeroconf."""
        if not ZEROCONF_AVAILABLE:
            logger.warning("Zeroconf not available for mDNS discovery")
            return []

        try:
            listener = HADiscoveryListener()
            zeroconf = Zeroconf()

            browser = ServiceBrowser(zeroconf, self.HA_SERVICE_TYPE, listener)

            # Wait for discovery (3 seconds)
            await asyncio.sleep(3)

            # Cleanup
            browser.cancel()
            zeroconf.close()

            self._discovered_instances = listener.services
            logger.info(f"Discovered {len(listener.services)} HA instances via mDNS")
            return listener.services

        except Exception as e:
            logger.error(f"mDNS discovery error: {e}")
            return []

    def _discover_from_env(self) -> List[Dict[str, Any]]:
        """Check environment variables for HA configuration."""
        ha_url = os.getenv("HOME_ASSISTANT_URL")
        if ha_url:
            return [
                {
                    "id": "ha_env",
                    "label": f"Home Assistant (from env: {ha_url})",
                    "description": "Configured via HOME_ASSISTANT_URL environment variable",
                    "metadata": {
                        "url": ha_url.rstrip("/"),
                        "source": "environment",
                    },
                }
            ]
        return []

    def _generate_pkce_challenge(self, state: str) -> Tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge.

        Args:
            state: OAuth state to associate with verifier

        Returns:
            (code_verifier, code_challenge) tuple
        """
        # Generate random code_verifier (43-128 chars, URL-safe)
        code_verifier = secrets.token_urlsafe(32)

        # Store for later token exchange
        self._pkce_verifiers[state] = code_verifier

        # Generate code_challenge = BASE64URL(SHA256(code_verifier))
        digest = hashlib.sha256(code_verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

        return code_verifier, code_challenge

    async def get_oauth_url(self, base_url: str, state: str) -> str:
        """Generate OAuth2 authorization URL for Home Assistant.

        Home Assistant uses IndieAuth-style OAuth2:
        - client_id is your application's website URL
        - No pre-registration required
        - Redirect URI must match client_id's host (or be declared via link tag)

        Args:
            base_url: Base URL of the HA instance (e.g., http://192.168.1.100:8123)
            state: State parameter for CSRF protection (session_id)

        Returns:
            Full OAuth authorization URL
        """
        # Generate PKCE challenge
        _, code_challenge = self._generate_pkce_challenge(state)

        # Build authorization URL
        # Per HA docs: client_id is your app's website, redirect_uri must match host
        params = {
            "client_id": self._client_id,
            "redirect_uri": f"{self._client_id}/v1/auth/oauth/ha_integration/callback",
            "response_type": "code",
            "state": state,
            # PKCE for additional security
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = f"{base_url.rstrip('/')}{self.OAUTH_AUTHORIZE_PATH}?{urlencode(params)}"

        logger.info(f"Generated HA OAuth URL for state: {state[:8]}...")
        return auth_url

    async def handle_oauth_callback(self, code: str, state: str, base_url: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens.

        Performs the OAuth2 token exchange with Home Assistant's token endpoint.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter for validation
            base_url: HA instance URL

        Returns:
            Token response with access_token, refresh_token, etc.
        """
        logger.info(f"Exchanging OAuth code for tokens (state: {state[:8]}...)")

        # Get stored PKCE verifier
        code_verifier = self._pkce_verifiers.pop(state, None)

        # Build token request
        token_url = f"{base_url.rstrip('/')}{self.OAUTH_TOKEN_PATH}"

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._client_id,
        }

        # Include PKCE verifier if we have one
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        logger.info("Successfully obtained HA access token")
                        return {
                            "access_token": token_data.get("access_token"),
                            "refresh_token": token_data.get("refresh_token"),
                            "token_type": token_data.get("token_type", "Bearer"),
                            "expires_in": token_data.get("expires_in", 1800),
                            "ha_auth_provider_type": token_data.get("ha_auth_provider_type"),
                            "ha_auth_provider_id": token_data.get("ha_auth_provider_id"),
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Token exchange failed: {response.status} - {error_text}")
                        return {
                            "error": "token_exchange_failed",
                            "error_description": f"HTTP {response.status}: {error_text}",
                        }

        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return {
                "error": "token_exchange_error",
                "error_description": str(e),
            }

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_instance":
            # Return discovered instances
            return self._discovered_instances

        elif step_id == "select_features":
            # Return available features
            return [
                {
                    "id": feature_id,
                    "label": feature["label"],
                    "description": feature["description"],
                    "metadata": {"default": feature["default"]},
                }
                for feature_id, feature in self.AVAILABLE_FEATURES.items()
            ]

        elif step_id == "select_cameras":
            # Return cameras from HA if we have a token
            access_token = context.get("access_token")
            base_url = context.get("base_url")
            if access_token and base_url:
                return await self._get_ha_cameras(base_url, access_token)
            return []

        return []

    async def _get_ha_cameras(self, base_url: str, access_token: str) -> List[Dict[str, Any]]:
        """Fetch camera entities from Home Assistant."""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/api/states",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status == 200:
                        entities = await response.json()
                        cameras = []
                        for entity in entities:
                            entity_id = entity.get("entity_id", "")
                            if entity_id.startswith("camera."):
                                cameras.append(
                                    {
                                        "id": entity_id,
                                        "label": entity.get("attributes", {}).get("friendly_name", entity_id),
                                        "description": f"Camera entity: {entity_id}",
                                        "metadata": {
                                            "entity_id": entity_id,
                                            "state": entity.get("state"),
                                        },
                                    }
                                )
                        return cameras

        except Exception as e:
            logger.error(f"Error fetching HA cameras: {e}")

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate HA configuration before applying.

        Performs:
        - Required field validation
        - URL format validation
        - Token connectivity test

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating HA configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required fields
        base_url = config.get("base_url")
        if not base_url:
            return False, "base_url is required"

        if not base_url.startswith(("http://", "https://")):
            return False, f"Invalid base_url: {base_url} (must start with http:// or https://)"

        access_token = config.get("access_token")
        if not access_token:
            return False, "access_token is required (complete OAuth flow first)"

        # Test connectivity with the token
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/api/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 401:
                        return False, "Access token is invalid or expired"
                    elif response.status != 200:
                        return False, f"HA connection failed: HTTP {response.status}"

        except aiohttp.ClientError as e:
            return False, f"HA connection error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

        # Validate enabled_features if present
        features = config.get("enabled_features", [])
        if features:
            valid_features = set(self.AVAILABLE_FEATURES.keys())
            invalid = set(features) - valid_features
            if invalid:
                return False, f"Invalid features: {invalid}"

        logger.info("HA configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying HA configuration")

        self._applied_config = config.copy()

        # Set environment variables for the HA service
        if config.get("base_url"):
            os.environ["HOME_ASSISTANT_URL"] = config["base_url"]
        if config.get("access_token"):
            os.environ["HOME_ASSISTANT_TOKEN"] = config["access_token"]
        if config.get("refresh_token"):
            os.environ["HOME_ASSISTANT_REFRESH_TOKEN"] = config["refresh_token"]

        # Log sanitized config
        safe_config = {k: ("***" if "token" in k.lower() else v) for k, v in config.items()}
        logger.info(f"HA configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
