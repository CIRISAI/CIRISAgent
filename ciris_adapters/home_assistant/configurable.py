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
                ip_address = addresses[0]

                # Prefer homeassistant.local if server name indicates it's available
                # The server field contains the hostname (e.g., "homeassistant.local.")
                server = getattr(info, "server", None)
                if server and "homeassistant" in server.lower():
                    # Strip trailing dot from mDNS name
                    hostname = server.rstrip(".")
                    host = hostname
                    logger.info(f"[mDNS DISCOVERY] Using hostname: {hostname}")
                else:
                    host = ip_address

                url = f"http://{host}:{port}"
                logger.info(f"[mDNS DISCOVERY] Found Home Assistant at {url}")
                logger.info(f"[mDNS DISCOVERY]   IP: {ip_address}, Host: {host}, Port: {port}, Name: {name}")
                self.services.append(
                    {
                        "id": f"ha_{ip_address}_{port}",
                        "label": f"Home Assistant ({host}:{port})",
                        "description": name.replace("._home-assistant._tcp.local.", ""),
                        "metadata": {
                            "host": host,
                            "ip": ip_address,
                            "port": port,
                            "name": name,
                            "url": url,
                        },
                    }
                )
            else:
                logger.warning(f"[mDNS DISCOVERY] Service {name} has no addresses")
        else:
            logger.warning(f"[mDNS DISCOVERY] Could not get service info for {name}")

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
        1. POST /adapters/home_assistant/configure/start
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

    # Default client ID for local deployments
    # For IndieAuth, this must match the redirect_uri host
    # Local deployments use http://127.0.0.1:8080 as client_id
    DEFAULT_CLIENT_ID = "http://127.0.0.1:8080"

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
            logger.info(f"[mDNS DISCOVERY] Complete: Found {len(listener.services)} HA instances")
            for svc in listener.services:
                logger.info(f"[mDNS DISCOVERY]   → {svc['metadata']['url']} ({svc['description']})")
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

    async def get_oauth_url(
        self,
        base_url: str,
        state: str,
        code_challenge: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """Generate OAuth2 authorization URL for Home Assistant.

        Home Assistant uses IndieAuth-style OAuth2:
        - client_id is your application's website URL
        - No pre-registration required
        - Redirect URI must match client_id's host (or be declared via link tag)

        For local/mobile deployments, pass callback_base_url to redirect to the
        local API instead of the production server.

        For Android with system browser, pass redirect_uri="ciris://oauth/callback"
        and platform="android" to use deep link callback. The deep link is handled
        by OAuthCallbackActivity which forwards to the local server.

        Note: This adapter generates its own PKCE challenge internally using
        _generate_pkce_challenge(). The code_challenge parameter is accepted
        for protocol conformance but not used directly.

        Args:
            base_url: Base URL of the HA instance (e.g., http://192.168.1.100:8123)
            state: State parameter for CSRF protection (session_id)
            code_challenge: PKCE code challenge (unused - HA adapter generates its own)
            callback_base_url: Optional base URL for OAuth callback (e.g., http://127.0.0.1:8080)
                             If provided, uses this for redirect_uri instead of client_id
            redirect_uri: Optional explicit redirect URI (e.g., ciris://oauth/callback for Android)
            platform: Optional platform hint (android, ios, web, desktop)

        Returns:
            Full OAuth authorization URL
        """
        # Generate PKCE challenge (we always generate our own, ignore passed code_challenge)
        _, generated_code_challenge = self._generate_pkce_challenge(state)

        # Determine redirect URI and client_id
        # Priority:
        # 1. If explicit redirect_uri provided (e.g., ciris:// for Android), use it
        # 2. If callback_base_url provided, use localhost callback
        # 3. Otherwise use production callback

        if redirect_uri and redirect_uri.startswith("ciris://"):
            # Android requested deep link - but Home Assistant requires:
            # 1. client_id must be a website URL
            # 2. redirect_uri host must match client_id host, OR
            # 3. redirect_uri must be whitelisted via <link rel='redirect_uri'> on client_id website
            #
            # Since we can't host a website with the link tag, we fall back to localhost redirect
            # which works because system browser CAN access localhost on the device.
            # The local Python server handles the callback.
            logger.info("=" * 60)
            logger.info("[OAUTH] ANDROID: Deep link requested but HA requires website client_id")
            logger.info(f"  Falling back to localhost redirect (system browser can access localhost)")
            logger.info("=" * 60)
            # Fall through to callback_base_url handling below

        if callback_base_url:
            # Local redirect - use local API as both client_id and redirect_uri
            client_id = callback_base_url.rstrip("/")
            final_redirect_uri = f"{client_id}/v1/system/adapters/configure/{state}/oauth/callback"
            logger.info("=" * 60)
            logger.info("[OAUTH] LOCAL CALLBACK REDIRECT URI:")
            logger.info(f"  callback_base_url: {callback_base_url}")
            logger.info(f"  client_id: {client_id}")
            logger.info(f"  state/session_id: {state}")
            logger.info(f"  FULL redirect_uri: {final_redirect_uri}")
            logger.info(f"  Expected route: /v1/system/adapters/configure/{{session_id}}/oauth/callback")
            logger.info("=" * 60)
        else:
            # No callback_base_url provided - use default localhost
            client_id = self._client_id  # http://127.0.0.1:8080
            final_redirect_uri = f"{client_id}/v1/system/adapters/configure/{state}/oauth/callback"
            logger.info(f"[OAUTH] Using default localhost callback: {final_redirect_uri}")

        # Build authorization URL
        params = {
            "client_id": client_id,
            "redirect_uri": final_redirect_uri,
            "response_type": "code",
            "state": state,
            # PKCE for additional security
            "code_challenge": generated_code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = f"{base_url.rstrip('/')}{self.OAUTH_AUTHORIZE_PATH}?{urlencode(params)}"

        logger.info(f"Generated HA OAuth URL for state: {state[:8]}...")
        return auth_url

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
        """Exchange authorization code for tokens.

        Performs the OAuth2 token exchange with Home Assistant's token endpoint.

        Note: This adapter stores its own PKCE verifier internally in _pkce_verifiers
        and retrieves it by state. The code_verifier parameter is accepted for
        protocol conformance but will be overridden by the stored value if available.

        Args:
            code: Authorization code from OAuth callback
            state: State parameter for validation
            base_url: HA instance URL
            code_verifier: PKCE verifier (optional - HA adapter uses internally stored one)
            callback_base_url: If provided, use this as client_id (for local OAuth)
            redirect_uri: If provided, the redirect_uri used in authorization (for Android deep links)
            platform: Platform hint (android, ios, web, desktop)

        Returns:
            Token response with access_token, refresh_token, etc.
        """
        logger.info(f"Exchanging OAuth code for tokens (state: {state[:8]}...)")

        # Get stored PKCE verifier (overrides any passed code_verifier)
        stored_verifier = self._pkce_verifiers.pop(state, None)
        if stored_verifier:
            code_verifier = stored_verifier

        # Build token request
        token_url = f"{base_url.rstrip('/')}{self.OAUTH_TOKEN_PATH}"

        # Determine client_id - must match what was used in get_oauth_url
        # For local/mobile deployments, we use the callback_base_url as client_id
        if callback_base_url:
            client_id = callback_base_url.rstrip("/")
        else:
            # Fallback - should not happen in local-only deployments
            client_id = "http://127.0.0.1:8080"
            logger.warning(f"[OAUTH CALLBACK] No callback_base_url provided, using default: {client_id}")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
        }
        logger.info(f"Token exchange with client_id: {client_id}")

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
            # Token may be at top level or nested in oauth_tokens
            access_token = context.get("access_token")
            if not access_token:
                oauth_tokens = context.get("oauth_tokens", {})
                access_token = oauth_tokens.get("access_token")

            base_url = context.get("base_url")
            logger.info(f"[select_cameras] base_url={base_url}, has_token={bool(access_token)}")

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

        # Get access_token - may be at top level or nested in oauth_tokens
        access_token = config.get("access_token")
        if not access_token:
            oauth_tokens = config.get("oauth_tokens", {})
            access_token = oauth_tokens.get("access_token")

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

        # Get tokens - may be at top level or nested in oauth_tokens
        oauth_tokens = config.get("oauth_tokens", {})
        access_token = config.get("access_token") or oauth_tokens.get("access_token")
        refresh_token = config.get("refresh_token") or oauth_tokens.get("refresh_token")

        # Set environment variables for the HA service
        if config.get("base_url"):
            os.environ["HOME_ASSISTANT_URL"] = config["base_url"]
        if access_token:
            os.environ["HOME_ASSISTANT_TOKEN"] = access_token
        if refresh_token:
            os.environ["HOME_ASSISTANT_REFRESH_TOKEN"] = refresh_token

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
