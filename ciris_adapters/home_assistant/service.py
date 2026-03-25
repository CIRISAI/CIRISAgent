"""
Home Assistant Integration Service.

Provides comprehensive Home Assistant integration with:
- Device control and automation triggering
- Sensor data retrieval
- Event detection from cameras (person, vehicle, motion, etc.)
- Camera frame extraction for vision pipeline

SAFE DOMAIN: Home automation only. Medical/health capabilities are prohibited.

Designed for CIRISHome hardware: Jetson + HA Yellow + Voice PE
"""

import asyncio
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

import aiohttp

from ciris_engine.schemas.services.core import ServiceCapabilities

from .schemas import (
    CameraAnalysisResult,
    CameraFrame,
    CameraStatus,
    DetectionEvent,
    EventType,
    HAAutomationResult,
    HADeviceState,
    HAEventType,
    HANotification,
)

logger = logging.getLogger(__name__)

# Optional imports for camera functionality
try:
    import cv2  # type: ignore[import-not-found]
    import numpy as np

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger.info("OpenCV not available - camera features disabled")


class HAIntegrationService:
    """
    Home Assistant integration service with multi-modal capabilities.

    Provides:
    - Chat bridge for notifications and conversations
    - Device control (lights, switches, automations)
    - Event detection (person, vehicle, motion via cameras)
    - Camera frame extraction for vision processing

    SAFE DOMAIN: Home automation only. Medical capabilities are blocked.
    """

    PROHIBITED_CAPABILITIES = {
        "medical",
        "health",
        "clinical",
        "patient",
        "vital",
        "diagnosis",
        "treatment",
        "symptom",
    }

    EVENT_TYPE_MAP = {
        "person": HAEventType.CAMERA_PERSON,
        "vehicle": HAEventType.CAMERA_VEHICLE,
        "animal": HAEventType.CAMERA_ANIMAL,
        "package": HAEventType.CAMERA_PACKAGE,
        "motion": HAEventType.CAMERA_MOTION,
        "activity": HAEventType.CAMERA_ACTIVITY,
    }

    def __init__(self) -> None:
        """Initialize the Home Assistant integration service."""
        # HA configuration - NOTE: Token is fetched dynamically via property
        # to support OAuth flows where token is set after adapter initialization
        self._ha_url: Optional[str] = None
        self._ha_token: Optional[str] = None

        # Camera configuration
        self.go2rtc_url = os.getenv("GO2RTC_SERVER_URL", "http://127.0.0.1:8554")
        self.camera_urls = self._parse_camera_urls()
        self.sensitivity = float(os.getenv("EVENT_DETECTION_SENSITIVITY", "0.7"))

        # State
        self._entity_cache: Dict[str, HADeviceState] = {}
        self._entity_list_cache: List[HADeviceState] = []  # Full list cache for get_all_entities
        self._cache_timestamp: Optional[datetime] = None  # Per-entity cache timestamp
        self._list_cache_timestamp: Optional[datetime] = None  # Full list cache timestamp
        self._cache_ttl = 30  # seconds
        self._detection_tasks: Dict[str, asyncio.Task[None]] = {}
        self._event_history: List[DetectionEvent] = []
        self._initialized = False
        self._init_failures = 0
        self._max_init_retries = 2  # Stop retrying after 2 failures

        logger.info(f"HAIntegrationService initialized for {self.ha_url}")
        logger.info(f"Configured {len(self.camera_urls)} cameras via go2rtc")

    @property
    def ha_url(self) -> str:
        """Get HA URL - fetched dynamically from env or cached value."""
        if self._ha_url:
            return self._ha_url
        return os.getenv("HOME_ASSISTANT_URL", "http://homeassistant.local:8123").rstrip("/")

    @ha_url.setter
    def ha_url(self, value: str) -> None:
        """Set HA URL explicitly."""
        self._ha_url = value.rstrip("/") if value else None

    @property
    def ha_token(self) -> Optional[str]:
        """Get HA token - fetched dynamically from env or cached value.

        This is critical for OAuth flows where the token is set via environment
        variable AFTER the service is initialized.
        """
        if self._ha_token:
            return self._ha_token
        token = os.getenv("HOME_ASSISTANT_TOKEN")
        if token:
            logger.debug(
                f"[HA TOKEN] Retrieved from env: {token[:20]}..."
                if len(token) > 20
                else f"[HA TOKEN] Retrieved from env: {token}"
            )
        return token

    @ha_token.setter
    def ha_token(self, value: Optional[str]) -> None:
        """Set HA token explicitly."""
        self._ha_token = value
        if value:
            logger.info(
                f"[HA TOKEN] Token set explicitly: {value[:20]}..." if len(value) > 20 else "[HA TOKEN] Token set"
            )

    @property
    def ma_enabled(self) -> bool:
        """Check if Music Assistant integration is available.

        MA is accessed through HA services (music_assistant.* domain).
        Returns True as MA availability is checked at runtime.
        """
        return True

    def _parse_camera_urls(self) -> Dict[str, str]:
        """Parse camera URLs from environment variable."""
        urls_env = os.getenv("WEBRTC_CAMERA_URLS", "")
        camera_urls: Dict[str, str] = {}

        if urls_env:
            for camera_def in urls_env.split(","):
                if ":" in camera_def:
                    parts = camera_def.split(":", 1)
                    if len(parts) == 2:
                        name, url = parts
                        camera_urls[name.strip()] = url.strip()

        return camera_urls

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities."""
        return ServiceCapabilities(
            service_name="ha_integration",
            actions=[
                "ha_chat_bridge",
                "ha_device_control",
                "ha_automation_trigger",
                "ha_sensor_data",
                "ha_event_detection",
                "ha_camera_frames",
            ],
            version="1.0.0",
            dependencies=[],
            metadata={
                "capabilities": [
                    "ha_chat_bridge",
                    "ha_device_control",
                    "ha_automation_trigger",
                    "ha_sensor_data",
                    "ha_event_detection",
                    "ha_camera_frames",
                    "provider:home_assistant",
                    "modality:vision:camera",
                    "modality:event:motion",
                    "domain:home_automation",
                ]
            },
        )

    async def _check_host_reachable(self, timeout_seconds: float = 1.0) -> bool:
        """Quick check if the HA host is reachable via TCP socket.

        This is much faster than a full HTTP request when the host is unreachable.
        Returns True if we can establish a TCP connection, False otherwise.
        """
        try:
            parsed = urlparse(self.ha_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 8123)

            # Run socket connect in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def try_connect() -> bool:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout_seconds)
                try:
                    sock.connect((host, port))
                    sock.close()
                    return True
                except (socket.timeout, socket.error, OSError):
                    return False
                finally:
                    try:
                        sock.close()
                    except Exception:
                        pass

            reachable = await loop.run_in_executor(None, try_connect)
            if not reachable:
                logger.debug(f"[HA] Host {host}:{port} not reachable (timeout={timeout_seconds}s)")
            return reachable
        except Exception as e:
            logger.debug(f"[HA] Reachability check failed: {e}")
            return False

    async def initialize(self) -> bool:
        """Initialize the service and verify connectivity.

        Uses a quick reachability check before attempting HTTP connection
        to fail fast when HA server is unreachable.
        """
        if self._initialized:
            return True

        if not self.ha_token:
            logger.warning("Cannot initialize - no HA token configured")
            return False

        # Quick reachability check (1 second timeout) - fail fast if host unreachable
        if not await self._check_host_reachable(timeout_seconds=1.0):
            logger.warning(f"[HA] Host unreachable: {self.ha_url} - skipping initialization")
            return False

        try:
            # Test HA connection with reduced timeout (3 seconds instead of 10)
            headers = self._get_headers()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as response:
                    if response.status == 200:
                        self._initialized = True
                        logger.info("Home Assistant connection verified")
                        return True
                    elif response.status == 401:
                        logger.warning("HA connection returned 401 - token expired, attempting refresh")
                        if await self._try_refresh_token():
                            # Retry with refreshed token
                            async with aiohttp.ClientSession() as retry_session:
                                async with retry_session.get(
                                    f"{self.ha_url}/api/",
                                    headers=self._get_headers(),
                                    timeout=aiohttp.ClientTimeout(total=3),
                                ) as retry_response:
                                    if retry_response.status == 200:
                                        self._initialized = True
                                        logger.info("Home Assistant connection verified after token refresh")
                                        return True
                                    logger.error(f"HA connection failed after refresh: status {retry_response.status}")
                        else:
                            logger.error("HA token refresh failed during initialization")
                        return False
                    else:
                        logger.error(f"HA connection failed with status {response.status}")
                        return False
        except asyncio.TimeoutError:
            logger.warning(f"[HA] Connection timeout (3s) to {self.ha_url}")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize HA integration: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for HA API calls."""
        return {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}

    # ========== Entity Resolution ==========

    async def resolve_entity_by_name(self, name_or_id: str) -> Optional[str]:
        """Resolve an entity by friendly name or entity_id.

        If name_or_id contains a dot and exists as entity_id, returns it directly.
        Otherwise, searches all entities for a matching friendly_name.

        Returns:
            The resolved entity_id, or None if not found.
        """
        # If it looks like an entity_id and exists, use it directly
        if "." in name_or_id:
            state = await self.get_device_state(name_or_id)
            if state and state.state not in ("unavailable", "unknown"):
                return name_or_id

        # Search by friendly name (case-insensitive)
        entities = await self.get_all_entities()
        name_lower = name_or_id.lower().strip()

        # Try exact match first
        for entity in entities:
            if entity.friendly_name and entity.friendly_name.lower() == name_lower:
                logger.info(f"[HA RESOLVE] Resolved friendly name '{name_or_id}' -> '{entity.entity_id}'")
                return entity.entity_id

        # Try partial match (friendly name contains the search term)
        for entity in entities:
            if entity.friendly_name and name_lower in entity.friendly_name.lower():
                logger.info(
                    f"[HA RESOLVE] Partial match '{name_or_id}' -> '{entity.entity_id}' (name: {entity.friendly_name})"
                )
                return entity.entity_id

        # Try if entity_id contains the search term (e.g., "bedroom" -> "light.bedroom_lamp")
        for entity in entities:
            if name_lower in entity.entity_id.lower():
                logger.info(f"[HA RESOLVE] Entity ID contains '{name_or_id}' -> '{entity.entity_id}'")
                return entity.entity_id

        logger.warning(f"[HA RESOLVE] Could not resolve '{name_or_id}' to any entity")
        return None

    # ========== Device Control ==========

    async def get_device_state(self, entity_id: str) -> Optional[HADeviceState]:
        """Get the current state of a Home Assistant entity."""
        if not self.ha_token:
            return None
        await self._ensure_initialized()

        # Check cache first
        if entity_id in self._entity_cache:
            cached = self._entity_cache[entity_id]
            if self._cache_timestamp:
                age = (datetime.now(timezone.utc) - self._cache_timestamp).total_seconds()
                if age < self._cache_ttl:
                    return cached

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/states/{entity_id}",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        state = HADeviceState(
                            entity_id=data.get("entity_id", entity_id),
                            state=data.get("state", "unknown"),
                            friendly_name=data.get("attributes", {}).get("friendly_name", entity_id),
                            last_changed=(
                                datetime.fromisoformat(data["last_changed"].replace("Z", "+00:00"))
                                if "last_changed" in data
                                else None
                            ),
                            last_updated=(
                                datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))
                                if "last_updated" in data
                                else None
                            ),
                            attributes=data.get("attributes", {}),
                            domain=entity_id.split(".")[0] if "." in entity_id else "",
                        )
                        self._entity_cache[entity_id] = state
                        self._cache_timestamp = datetime.now(timezone.utc)
                        return state
                    else:
                        logger.warning(f"Failed to get state for {entity_id}: status {response.status}")
        except Exception as e:
            logger.error(f"Error getting device state: {e}")

        return None

    async def control_device(
        self, entity_id: str, action: str, _retry: bool = True, **kwargs: Any
    ) -> HAAutomationResult:
        """Control a Home Assistant device."""
        logger.info("=" * 60)
        logger.info("[HA DEVICE CONTROL] Starting device control request")
        logger.info(f"  entity_id: {entity_id}")
        logger.info(f"  action: {action}")
        logger.info(f"  kwargs: {kwargs}")
        logger.info(f"  ha_url: {self.ha_url}")

        # Ensure initialized (lazy init if token appeared after startup)
        await self._ensure_initialized()

        token = self.ha_token
        if not token:
            logger.error("[HA DEVICE CONTROL] NO TOKEN AVAILABLE!")
            logger.error(f"  _ha_token (cached): {self._ha_token}")
            logger.error(
                f"  HOME_ASSISTANT_TOKEN env: {os.getenv('HOME_ASSISTANT_TOKEN', '<not set>')[:20] if os.getenv('HOME_ASSISTANT_TOKEN') else '<not set>'}"
            )
            logger.info("=" * 60)
            return HAAutomationResult(
                entity_id=entity_id,
                action=action,
                success=False,
                error="Home Assistant not configured - no token available",
            )

        logger.info(f"  token: {token[:20]}..." if len(token) > 20 else f"  token: {token}")

        # Map actions to HA services
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        service_map = {
            "turn_on": f"{domain}/turn_on",
            "turn_off": f"{domain}/turn_off",
            "toggle": f"{domain}/toggle",
            "trigger": "automation/trigger",
        }

        service = service_map.get(action, f"{domain}/{action}")
        url = f"{self.ha_url}/api/services/{service}"
        logger.info(f"  service: {service}")
        logger.info(f"  full URL: {url}")

        try:
            payload: Dict[str, Any] = {"entity_id": entity_id}
            payload.update(kwargs)
            logger.info(f"  payload: {payload}")

            headers = self._get_headers()
            logger.info(f"  headers: Authorization=Bearer {token[:20]}..., Content-Type=application/json")

            async with aiohttp.ClientSession() as session:
                logger.info(f"[HA DEVICE CONTROL] Sending POST request to {url}")
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    status = response.status
                    response_text = await response.text()
                    logger.info(f"[HA DEVICE CONTROL] Response status: {status}")
                    logger.info(
                        f"[HA DEVICE CONTROL] Response body: {response_text[:500]}"
                        if len(response_text) > 500
                        else f"[HA DEVICE CONTROL] Response body: {response_text}"
                    )

                    # HA returns 200 even for non-existent entities!
                    # Check if response body contains any state changes
                    # Empty array [] means the entity wasn't found/controlled
                    response_data = None
                    try:
                        import json

                        response_data = json.loads(response_text) if response_text else []
                    except json.JSONDecodeError:
                        response_data = []

                    # Success only if HTTP 200 AND entity was actually affected
                    success = status == 200 and (isinstance(response_data, list) and len(response_data) > 0)

                    if not success:
                        if status == 200 and (not response_data or len(response_data) == 0):
                            # HA returned success but no entities were affected
                            # This can mean: entity doesn't exist, entity doesn't support action,
                            # or action had no effect (e.g., media_play with nothing paused)
                            if action in ("media_play", "media_pause", "media_stop"):
                                logger.error(
                                    f"[HA DEVICE CONTROL] FAILED! Action '{action}' had no effect on '{entity_id}'. "
                                    f"For media_play: ensure something is paused/queued. "
                                    f"To play new music, use Music Assistant tools (ma_search, ma_play)."
                                )
                            else:
                                logger.error(
                                    f"[HA DEVICE CONTROL] FAILED! Action '{action}' had no effect on '{entity_id}' "
                                    f"(entity may not exist or doesn't support this action)"
                                )
                        else:
                            logger.error(f"[HA DEVICE CONTROL] FAILED! Status {status}")
                        if status == 401:
                            logger.error("[HA DEVICE CONTROL] 401 Unauthorized - Token expired, attempting refresh")
                            if _retry and await self._try_refresh_token():
                                logger.info("[HA DEVICE CONTROL] Token refreshed, retrying...")
                                return await self.control_device(entity_id, action, _retry=False, **kwargs)
                            logger.error("[HA DEVICE CONTROL] Token refresh failed or retry exhausted")
                        elif status == 403:
                            logger.error("[HA DEVICE CONTROL] 403 Forbidden - Token lacks required permissions")
                        elif status == 404:
                            logger.error(f"[HA DEVICE CONTROL] 404 Not Found - Service {service} not found")

                    # Build appropriate error message
                    error_msg = None
                    if not success:
                        if status == 200 and (not response_data or len(response_data) == 0):
                            # More specific error based on action type
                            if action in ("media_play", "media_pause", "media_stop"):
                                error_msg = (
                                    f"Action '{action}' had no effect on '{entity_id}'. "
                                    f"media_play resumes paused content; to play NEW music, use Music Assistant tools (ma_search, ma_play)."
                                )
                            else:
                                error_msg = (
                                    f"Action '{action}' had no effect on '{entity_id}'. "
                                    f"Entity may not exist or doesn't support this action. "
                                    f"Use ha_list_entities to verify entity availability."
                                )
                        else:
                            error_msg = f"Status {status}: {response_text[:200]}"

                    logger.info("=" * 60)
                    return HAAutomationResult(
                        entity_id=entity_id,
                        action=action,
                        success=success,
                        error=error_msg,
                    )
        except Exception as e:
            logger.error(f"[HA DEVICE CONTROL] Exception: {e}")
            import traceback

            logger.error(f"[HA DEVICE CONTROL] Traceback: {traceback.format_exc()}")
            logger.info("=" * 60)
            return HAAutomationResult(
                entity_id=entity_id,
                action=action,
                success=False,
                error=str(e),
            )

    async def trigger_automation(self, automation_id: str) -> HAAutomationResult:
        """Trigger a Home Assistant automation."""
        return await self.control_device(automation_id, "trigger")

    # ========== Notifications ==========

    async def send_notification(self, notification: HANotification) -> bool:
        """Send a notification via Home Assistant."""
        if not self.ha_token:
            return False

        try:
            payload: Dict[str, Any] = {
                "title": notification.title,
                "message": notification.message,
            }
            if notification.data:
                payload["data"] = notification.data

            service = "notify/notify"
            if notification.target:
                service = f"notify/{notification.target}"

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}/api/services/{service}",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    # ========== Token Refresh ==========

    async def _try_refresh_token(self) -> bool:
        """Attempt to refresh the HA access token using the refresh token.

        Home Assistant OAuth2 token refresh requires:
        - POST to /auth/token
        - Content-Type: application/x-www-form-urlencoded
        - Payload: client_id, grant_type=refresh_token, refresh_token
        """
        refresh_token = os.getenv("HOME_ASSISTANT_REFRESH_TOKEN")
        client_id = os.getenv("HOME_ASSISTANT_CLIENT_ID")

        if not refresh_token:
            logger.warning("[HA] Token refresh: No refresh_token available")
            return False
        if not client_id:
            logger.warning("[HA] Token refresh: No client_id available")
            return False

        try:
            logger.info("[HA] Attempting token refresh...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}/auth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        new_access_token = token_data.get("access_token")
                        if new_access_token:
                            # Update environment variable and cached token
                            os.environ["HOME_ASSISTANT_TOKEN"] = new_access_token
                            self._ha_token = new_access_token
                            logger.info("[HA] Token refreshed successfully!")
                            return True
                        logger.error("[HA] Token refresh response missing access_token")
                    else:
                        body = await response.text()
                        logger.error(f"[HA] Token refresh failed: HTTP {response.status} - {body[:200]}")
        except Exception as e:
            logger.error(f"[HA] Token refresh exception: {e}")
        return False

    # ========== Sensor Data ==========

    async def _ensure_initialized(self) -> bool:
        """Lazy initialization - retry if token has become available since startup."""
        if self._initialized:
            return True
        if self._init_failures >= self._max_init_retries:
            return False
        if self.ha_token:
            logger.info("[HA] Token now available, attempting lazy initialization...")
            result = await self.initialize()
            if not result:
                self._init_failures += 1
                if self._init_failures >= self._max_init_retries:
                    logger.warning(
                        f"[HA] Initialization failed {self._init_failures} times, giving up. "
                        "Will not retry until adapter restart."
                    )
            return result
        return False

    async def get_all_entities(self, _retry: bool = True) -> List[HADeviceState]:
        """Get all Home Assistant entities. Returns cached results if fresh."""
        if not self.ha_token:
            return []

        # Return cached results if still fresh (uses list-specific timestamp)
        if self._list_cache_timestamp and self._entity_list_cache:
            age = (datetime.now(timezone.utc) - self._list_cache_timestamp).total_seconds()
            if age < self._cache_ttl:
                return self._entity_list_cache

        # Ensure we're initialized (respects max retry limit)
        if not await self._ensure_initialized():
            return self._entity_list_cache  # Return stale cache if available, else empty

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/states",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status == 200:
                        entities = await response.json()
                        result = []
                        for entity in entities:
                            attrs = entity.get("attributes", {})
                            state = HADeviceState(
                                entity_id=entity.get("entity_id", ""),
                                state=entity.get("state", "unknown"),
                                friendly_name=attrs.get("friendly_name", ""),
                                attributes=attrs,
                                domain=entity.get("entity_id", "").split(".")[0],
                            )
                            result.append(state)
                            self._entity_cache[state.entity_id] = state
                        now = datetime.now(timezone.utc)
                        self._cache_timestamp = now
                        self._list_cache_timestamp = now
                        self._entity_list_cache = result
                        logger.info(f"[HA] get_all_entities: Retrieved {len(result)} entities")
                        return result
                    elif response.status == 401 and _retry:
                        logger.warning("[HA] get_all_entities: 401 - attempting token refresh")
                        if await self._try_refresh_token():
                            return await self.get_all_entities(_retry=False)
                        logger.error("[HA] get_all_entities: Token refresh failed")
                    else:
                        body = await response.text()
                        logger.error(f"[HA] get_all_entities: HTTP {response.status} - {body[:200]}")
        except Exception as e:
            logger.error(f"[HA] get_all_entities: Exception - {e}")

        return self._entity_list_cache  # Return stale cache on failure

    async def get_sensors_by_domain(self, domain: str) -> List[HADeviceState]:
        """Get all entities in a specific domain (sensor, light, switch, etc.)."""
        entities = await self.get_all_entities()
        return [e for e in entities if e.domain == domain]

    # ========== Music Assistant Functionality ==========
    # These methods use HA service calls to interact with Music Assistant.
    # MA must be installed as an HA integration (music_assistant.* services).

    async def _get_ma_config_entry_id(self) -> Optional[str]:
        """Get the Music Assistant config entry ID from Home Assistant."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/config/config_entries/entry",
                    headers=self._get_headers(),
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        entries = await response.json()
                        for entry in entries:
                            if entry.get("domain") == "music_assistant":
                                entry_id: str | None = entry.get("entry_id")
                                logger.info(f"[MA] Found config_entry_id: {entry_id}")
                                return entry_id
                    logger.warning("[MA] Could not find music_assistant config entry")
                    return None
        except Exception as e:
            logger.error(f"[MA] Error getting config entry: {e}")
            return None

    async def ma_search(
        self,
        query: str,
        media_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search Music Assistant library via HA service call.

        Uses music_assistant.search service through HA API.

        Args:
            query: Search query string
            media_types: Optional list of types to search (artist, album, track, playlist, radio)
            limit: Maximum results per type (default 10)

        Returns:
            Dict with search results
        """
        try:
            # Get MA config entry ID (required for search)
            config_entry_id = await self._get_ma_config_entry_id()

            # Use HA service call for MA search
            # Service: music_assistant.search
            service_data: Dict[str, Any] = {
                "name": query,
                "limit": limit,
            }
            if config_entry_id:
                service_data["config_entry_id"] = config_entry_id
            if media_types:
                service_data["media_type"] = media_types

            logger.info(f"[MA] Search request: {service_data}")

            async with aiohttp.ClientSession() as session:
                # Use ?return_response to get search results back
                async with session.post(
                    f"{self.ha_url}/api/services/music_assistant/search?return_response",
                    json=service_data,
                    headers={
                        "Authorization": f"Bearer {self.ha_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response_body = await response.text()
                    logger.info(f"[MA] Search response: HTTP {response.status}, body: {response_body[:500]}")

                    if response.status == 200:
                        # Try to parse as JSON
                        try:
                            data = await response.json() if response_body else []
                        except Exception:
                            data = []

                        # HA service calls often return `[]` on success
                        # The actual results may be delivered via events
                        if not data or data == []:
                            logger.info(f"[MA] Search '{query}': service accepted (async results via events)")
                            return {
                                "success": True,
                                "query": query,
                                "results": [],
                                "note": "Search request accepted. Results may be async via events.",
                            }

                        logger.info(f"[MA] Search '{query}' via HA: got {len(data)} results")
                        return {"success": True, "query": query, "results": data}
                    elif response.status == 404:
                        return {
                            "success": False,
                            "error": "Music Assistant integration not found in Home Assistant",
                        }
                    else:
                        logger.error(f"[MA] Search failed: HTTP {response.status} - {response_body[:200]}")
                        return {
                            "success": False,
                            "error": f"MA search failed: HTTP {response.status}",
                        }
        except Exception as e:
            logger.error(f"[MA] Search exception: {e}")
            return {"error": str(e)}

    async def ma_play(
        self,
        media_id: str,
        player_id: Optional[str] = None,
        media_type: str = "track",
        enqueue: str = "play",
    ) -> Dict[str, Any]:
        """Play media on Music Assistant via HA service call.

        Uses music_assistant.play_media service through HA API.

        Args:
            media_id: Media name, URI, or ID to play
            player_id: Target player entity ID (e.g., media_player.mass_living_room)
            media_type: Type of media (track, album, artist, playlist)
            enqueue: Queue behavior - play, next, add, replace

        Returns:
            Dict with play result including verification status
        """
        try:
            # Build service data - config_entry_id is NOT required and causes 400 if invalid
            service_data: Dict[str, Any] = {
                "media_id": media_id,
                "media_type": media_type,
                "enqueue": enqueue,
            }
            if player_id:
                service_data["entity_id"] = player_id

            logger.info(f"[MA] Play request: {service_data}")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}/api/services/music_assistant/play_media",
                    json=service_data,
                    headers={
                        "Authorization": f"Bearer {self.ha_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response_body = await response.text()
                    logger.info(f"[MA] Play response: HTTP {response.status}, body: {response_body[:500]}")

                    if response.status == 404:
                        return {
                            "success": False,
                            "error": "Music Assistant integration not found in Home Assistant",
                        }
                    elif response.status != 200:
                        logger.error(f"[MA] Play failed: HTTP {response.status} - {response_body[:200]}")
                        return {
                            "success": False,
                            "error": f"MA play failed: HTTP {response.status}",
                            "details": response_body[:200],
                        }

                    # HTTP 200 received - but we need to verify playback actually started
                    # HA returns 200 for any valid service call even if media wasn't found

                    # Wait briefly for player state to update
                    await asyncio.sleep(2)

                    # Verify playback if we have a player_id
                    if player_id:
                        player_state = await self.get_device_state(player_id)
                        if player_state:
                            current_state = player_state.state
                            media_title = player_state.attributes.get("media_title", "")
                            media_artist = player_state.attributes.get("media_artist", "")
                            logger.info(
                                f"[MA] Player state after play: {current_state}, "
                                f"title='{media_title}', artist='{media_artist}'"
                            )

                            if current_state == "playing":
                                return {
                                    "success": True,
                                    "media_id": media_id,
                                    "player": player_id,
                                    "verified": True,
                                    "now_playing": {
                                        "title": media_title,
                                        "artist": media_artist,
                                    },
                                }
                            else:
                                # Player exists but not playing
                                return {
                                    "success": False,
                                    "error": f"Playback did not start. Player state: {current_state}",
                                    "player": player_id,
                                    "suggestion": (
                                        "The track may not exist in Music Assistant, or the player "
                                        "may not be available. Try ma_search first to verify the track exists, "
                                        "and ma_players to list available players."
                                    ),
                                }
                        else:
                            return {
                                "success": False,
                                "error": f"Could not verify player state for '{player_id}'",
                                "suggestion": "The player entity may not exist. Use ma_players to list available players.",
                            }

                    # No player_id specified - can't verify, return cautious response
                    return {
                        "success": True,
                        "media_id": media_id,
                        "verified": False,
                        "warning": "No player specified - could not verify playback started",
                    }

        except Exception as e:
            logger.error(f"[MA] Play exception: {e}")
            return {"success": False, "error": str(e)}

    async def ma_get_players(self) -> Dict[str, Any]:
        """Get all Music Assistant players via HA entity query.

        Finds all media_player entities that belong to Music Assistant.

        Returns:
            Dict with player list and states
        """
        try:
            # Get all media_player entities and filter for MA players
            entities = await self.get_all_entities()
            ma_players = [
                {
                    "entity_id": e.entity_id,
                    "name": e.friendly_name,
                    "state": e.state,
                    "attributes": e.attributes,
                }
                for e in entities
                if e.domain == "media_player"
                and (
                    e.entity_id.startswith("media_player.mass_")
                    or e.attributes.get("mass_player_id")
                    or e.attributes.get("mass_player_type")  # MA-managed player
                    or e.attributes.get("app_id") == "music_assistant"  # Currently using MA
                    or "music_assistant" in str(e.attributes.get("friendly_name", "")).lower()
                )
            ]

            if not ma_players:
                # Fall back to all media players if no MA-specific ones found
                logger.warning("[MA] No Music Assistant players found, returning all media players")
                ma_players = [
                    {
                        "entity_id": e.entity_id,
                        "name": e.friendly_name,
                        "state": e.state,
                    }
                    for e in entities
                    if e.domain == "media_player"
                ]

            logger.info(f"[MA] Get players: found {len(ma_players)} (MA-controlled)")
            return {"success": True, "players": ma_players}
        except Exception as e:
            logger.error(f"[MA] Get players exception: {e}")
            return {"error": str(e)}

    async def ma_get_queue(self, player_id: str) -> Dict[str, Any]:
        """Get the queue for a Music Assistant player.

        Queries player attributes for queue info.

        Args:
            player_id: Player entity ID

        Returns:
            Dict with queue info from player attributes
        """
        try:
            state = await self.get_device_state(player_id)
            if not state:
                return {"error": f"Player not found: {player_id}"}

            # Extract queue info from player attributes
            attrs = state.attributes
            queue_info = {
                "player_id": player_id,
                "state": state.state,
                "current_track": attrs.get("media_title"),
                "current_artist": attrs.get("media_artist"),
                "current_album": attrs.get("media_album_name"),
                "queue_position": attrs.get("queue_position"),
                "queue_size": attrs.get("queue_size"),
                "shuffle": attrs.get("shuffle"),
                "repeat": attrs.get("repeat"),
            }

            logger.info(
                f"[MA] Get queue for {player_id}: position {queue_info.get('queue_position')}/{queue_info.get('queue_size')}"
            )
            return {"success": True, "queue": queue_info}
        except Exception as e:
            logger.error(f"[MA] Get queue exception: {e}")
            return {"error": str(e)}

    async def ma_browse(self, media_type: str = "artists", limit: int = 25) -> Dict[str, Any]:
        """Browse Music Assistant library via HA service call.

        Uses music_assistant.get_library service.

        Args:
            media_type: Category to browse (artists, albums, tracks, playlists)
            limit: Maximum results

        Returns:
            Dict with browsable items
        """
        try:
            # Get MA config entry ID (may be required)
            config_entry_id = await self._get_ma_config_entry_id()

            service_data: Dict[str, Any] = {
                "media_type": media_type,
                "limit": limit,
            }
            if config_entry_id:
                service_data["config_entry_id"] = config_entry_id

            logger.info(f"[MA] Browse request: {service_data}")

            async with aiohttp.ClientSession() as session:
                # Note: ?return_response required for HA 2024.3+ to get response data
                async with session.post(
                    f"{self.ha_url}/api/services/music_assistant/get_library?return_response",
                    json=service_data,
                    headers={
                        "Authorization": f"Bearer {self.ha_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response_body = await response.text()
                    logger.info(f"[MA] Browse response: HTTP {response.status}, body: {response_body[:500]}")

                    if response.status == 200:
                        try:
                            data = await response.json() if response_body else []
                        except Exception:
                            data = []
                        logger.info(f"[MA] Browse '{media_type}' via HA: success")
                        return {"success": True, "media_type": media_type, "items": data}
                    elif response.status == 404:
                        return {"success": False, "error": "Music Assistant integration not found in Home Assistant"}
                    else:
                        logger.error(f"[MA] Browse failed: HTTP {response.status} - {response_body[:200]}")
                        return {"success": False, "error": f"MA browse failed: HTTP {response.status}"}
        except Exception as e:
            logger.error(f"[MA] Browse exception: {e}")
            return {"error": str(e)}

    # ========== Camera Functionality ==========

    async def get_available_cameras(self) -> List[str]:
        """Get list of available camera names."""
        return list(self.camera_urls.keys())

    async def get_camera_stream_url(self, camera_name: str) -> Optional[str]:
        """Get RTSP stream URL for a camera."""
        return self.camera_urls.get(camera_name)

    async def get_camera_status(
        self, camera_name: Optional[str] = None
    ) -> Union[CameraStatus, Dict[str, CameraStatus]]:
        """Get status of camera(s)."""
        if not OPENCV_AVAILABLE:
            if camera_name:
                return CameraStatus(
                    camera_name=camera_name,
                    stream_url=self.camera_urls.get(camera_name, ""),
                    is_online=False,
                    last_check=datetime.now(timezone.utc),
                )
            return {}

        if camera_name:
            url = self.camera_urls.get(camera_name, "")
            is_online = False
            if url:
                cap = cv2.VideoCapture(url)
                is_online = cap.isOpened()
                cap.release()
            return CameraStatus(
                camera_name=camera_name,
                stream_url=url,
                is_online=is_online,
                last_check=datetime.now(timezone.utc),
            )

        # Get all camera statuses
        results: Dict[str, CameraStatus] = {}
        for name, url in self.camera_urls.items():
            cap = cv2.VideoCapture(url)
            is_online = cap.isOpened()
            cap.release()
            results[name] = CameraStatus(
                camera_name=name,
                stream_url=url,
                is_online=is_online,
                last_check=datetime.now(timezone.utc),
            )
        return results

    async def extract_camera_frames(
        self, camera_name: str, num_frames: int = 5, interval_ms: int = 200
    ) -> List[CameraFrame]:
        """
        Extract frames from a camera stream.

        Returns frame metadata (not raw image data) for type safety.
        Use with vision pipeline for analysis.
        """
        if not OPENCV_AVAILABLE:
            logger.warning("OpenCV not available for frame extraction")
            return []

        url = self.camera_urls.get(camera_name)
        if not url:
            logger.error(f"Camera {camera_name} not configured")
            return []

        frames: List[CameraFrame] = []
        try:
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                logger.error(f"Could not open stream for {camera_name}")
                return []

            for i in range(num_frames):
                ret, frame = cap.read()
                if ret:
                    height, width = frame.shape[:2]
                    channels = frame.shape[2] if len(frame.shape) > 2 else 1
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    brightness = float(np.mean(gray))

                    frames.append(
                        CameraFrame(
                            camera_name=camera_name,
                            timestamp=datetime.now(timezone.utc),
                            width=width,
                            height=height,
                            channels=channels,
                            brightness=brightness,
                            motion_detected=False,  # Set by detection loop
                            frame_index=i,
                        )
                    )
                    await asyncio.sleep(interval_ms / 1000.0)
                else:
                    break

            cap.release()
            logger.info(f"Extracted {len(frames)} frames from {camera_name}")

        except Exception as e:
            logger.error(f"Error extracting frames from {camera_name}: {e}")

        return frames

    async def analyze_camera_feed(self, camera_name: str, duration_seconds: int = 10) -> CameraAnalysisResult:
        """
        Analyze camera feed for motion detection.

        Returns analysis result with motion detection and brightness metrics.
        """
        if not OPENCV_AVAILABLE:
            return CameraAnalysisResult(
                camera_name=camera_name,
                duration_seconds=duration_seconds,
                error="OpenCV not available",
            )

        url = self.camera_urls.get(camera_name)
        if not url:
            return CameraAnalysisResult(
                camera_name=camera_name,
                duration_seconds=duration_seconds,
                error=f"Camera {camera_name} not configured",
            )

        try:
            cap = cv2.VideoCapture(url)
            if not cap.isOpened():
                return CameraAnalysisResult(
                    camera_name=camera_name,
                    duration_seconds=duration_seconds,
                    error=f"Could not open stream for {camera_name}",
                )

            frame_count = 0
            brightness_sum = 0.0
            motion_detected = False
            previous_frame: Optional[Any] = None
            motion_threshold = 5000

            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < duration_seconds:
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness_sum += float(np.mean(gray))

                if previous_frame is not None:
                    diff = cv2.absdiff(previous_frame, gray)
                    non_zero_count = int(np.count_nonzero(diff > 30))
                    if non_zero_count > motion_threshold:
                        motion_detected = True

                previous_frame = gray.copy()
                await asyncio.sleep(0.1)

            cap.release()

            return CameraAnalysisResult(
                camera_name=camera_name,
                duration_seconds=duration_seconds,
                frames_analyzed=frame_count,
                motion_detected=motion_detected,
                average_brightness=brightness_sum / frame_count if frame_count > 0 else 0.0,
            )

        except Exception as e:
            logger.error(f"Error analyzing camera {camera_name}: {e}")
            return CameraAnalysisResult(
                camera_name=camera_name,
                duration_seconds=duration_seconds,
                error=str(e),
            )

    # ========== Event Detection ==========

    async def detect_motion(self, camera_name: str, sensitivity: float = 0.5) -> bool:
        """Quick motion detection on camera feed."""
        result = await self.analyze_camera_feed(camera_name, duration_seconds=3)
        return result.motion_detected

    async def start_event_detection(self, camera_name: str) -> bool:
        """Start continuous event detection for a camera."""
        if camera_name in self._detection_tasks:
            logger.warning(f"Detection already running for {camera_name}")
            return False

        if not OPENCV_AVAILABLE:
            logger.error("OpenCV not available for event detection")
            return False

        task = asyncio.create_task(self._detection_loop(camera_name))
        self._detection_tasks[camera_name] = task
        logger.info(f"Started event detection for {camera_name}")
        return True

    async def stop_event_detection(self, camera_name: str) -> bool:
        """Stop event detection for a camera."""
        if camera_name in self._detection_tasks:
            self._detection_tasks[camera_name].cancel()
            del self._detection_tasks[camera_name]
            logger.info(f"Stopped event detection for {camera_name}")
            return True
        return False

    async def _detection_loop(self, camera_name: str) -> None:
        """Main detection loop for a camera."""
        url = self.camera_urls.get(camera_name)
        if not url:
            return

        previous_frame: Optional[Any] = None
        last_event_time: Dict[str, datetime] = {}
        cooldown_seconds = 10

        while True:
            try:
                cap = cv2.VideoCapture(url)
                if not cap.isOpened():
                    await asyncio.sleep(5)
                    continue

                ret, frame = cap.read()
                cap.release()

                if not ret:
                    await asyncio.sleep(5)
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                # Motion detection
                if previous_frame is not None:
                    diff = cv2.absdiff(previous_frame, gray)
                    _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
                    changed_pixels = int(np.count_nonzero(thresh))
                    total_pixels = int(thresh.shape[0] * thresh.shape[1])
                    change_pct = float(changed_pixels) / float(total_pixels)

                    if change_pct > 0.02:  # 2% threshold
                        now = datetime.now(timezone.utc)
                        last_motion = last_event_time.get("motion", datetime.min.replace(tzinfo=timezone.utc))
                        if (now - last_motion).total_seconds() > cooldown_seconds:
                            event = DetectionEvent(
                                event_type=EventType.MOTION,
                                camera_name=camera_name,
                                confidence=min(change_pct * 10, 1.0),
                                timestamp=now,
                                zones=[],
                                description=f"Motion detected ({change_pct:.1%} change)",
                                ha_event_type=HAEventType.CAMERA_MOTION,
                            )
                            self._event_history.append(event)
                            await self._send_ha_event(event)
                            last_event_time["motion"] = now

                previous_frame = gray.copy()
                await asyncio.sleep(3)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Detection loop error for {camera_name}: {e}")
                await asyncio.sleep(5)

    async def _send_ha_event(self, event: DetectionEvent) -> bool:
        """Send detection event to Home Assistant."""
        if not self.ha_token:
            return False

        try:
            payload = {
                "type": "camera_event",
                "event_type": event.ha_event_type,
                "camera": event.camera_name,
                "confidence": event.confidence,
                "description": event.description,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ha_url}/api/events/ciris_camera_event",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Failed to send HA event: {e}")
            return False

    def get_event_history(self, limit: int = 100) -> List[DetectionEvent]:
        """Get recent detection events."""
        return self._event_history[-limit:]

    async def cleanup(self) -> None:
        """Clean up resources."""
        for camera_name in list(self._detection_tasks.keys()):
            await self.stop_event_detection(camera_name)
        self._entity_cache.clear()
        self._entity_list_cache.clear()
        logger.info("HAIntegrationService cleaned up")
