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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

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
    import cv2
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
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 30  # seconds
        self._detection_tasks: Dict[str, asyncio.Task[None]] = {}
        self._event_history: List[DetectionEvent] = []
        self._initialized = False

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

    async def initialize(self) -> bool:
        """Initialize the service and verify connectivity."""
        if self._initialized:
            return True

        if not self.ha_token:
            logger.warning("Cannot initialize - no HA token configured")
            return False

        try:
            # Test HA connection
            headers = self._get_headers()
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ha_url}/api/",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        self._initialized = True
                        logger.info("Home Assistant connection verified")
                        return True
                    else:
                        logger.error(f"HA connection failed with status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Failed to initialize HA integration: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for HA API calls."""
        return {"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"}

    # ========== Device Control ==========

    async def get_device_state(self, entity_id: str) -> Optional[HADeviceState]:
        """Get the current state of a Home Assistant entity."""
        if not self.ha_token:
            return None

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

    async def control_device(self, entity_id: str, action: str, **kwargs: Any) -> HAAutomationResult:
        """Control a Home Assistant device."""
        logger.info("=" * 60)
        logger.info("[HA DEVICE CONTROL] Starting device control request")
        logger.info(f"  entity_id: {entity_id}")
        logger.info(f"  action: {action}")
        logger.info(f"  kwargs: {kwargs}")
        logger.info(f"  ha_url: {self.ha_url}")

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

                    success = status == 200
                    if not success:
                        logger.error(f"[HA DEVICE CONTROL] FAILED! Status {status}")
                        if status == 401:
                            logger.error("[HA DEVICE CONTROL] 401 Unauthorized - Token may be expired or invalid")
                        elif status == 403:
                            logger.error("[HA DEVICE CONTROL] 403 Forbidden - Token lacks required permissions")
                        elif status == 404:
                            logger.error(f"[HA DEVICE CONTROL] 404 Not Found - Service {service} not found")

                    logger.info("=" * 60)
                    return HAAutomationResult(
                        entity_id=entity_id,
                        action=action,
                        success=success,
                        error=None if success else f"Status {status}: {response_text[:200]}",
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

    # ========== Sensor Data ==========

    async def get_all_entities(self) -> List[HADeviceState]:
        """Get all Home Assistant entities."""
        if not self.ha_token:
            return []

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
                            state = HADeviceState(
                                entity_id=entity.get("entity_id", ""),
                                state=entity.get("state", "unknown"),
                                friendly_name=entity.get("attributes", {}).get("friendly_name", ""),
                                attributes=entity.get("attributes", {}),
                                domain=entity.get("entity_id", "").split(".")[0],
                            )
                            result.append(state)
                            self._entity_cache[state.entity_id] = state
                        self._cache_timestamp = datetime.now(timezone.utc)
                        return result
        except Exception as e:
            logger.error(f"Error getting entities: {e}")

        return []

    async def get_sensors_by_domain(self, domain: str) -> List[HADeviceState]:
        """Get all entities in a specific domain (sensor, light, switch, etc.)."""
        entities = await self.get_all_entities()
        return [e for e in entities if e.domain == domain]

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
        logger.info("HAIntegrationService cleaned up")
