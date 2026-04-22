"""
Home Assistant Integration Module for CIRIS.

Provides enhanced Home Assistant integration with multi-modal capabilities:
- Chat bridge for HA notifications and conversations
- Device control (lights, switches, automations)
- Event detection (person, vehicle, motion, etc.)
- Camera frame extraction for vision processing

Designed for the CIRISHome hardware stack:
- NVIDIA Jetson for local AI processing
- Home Assistant Yellow for smart home control
- Voice PE for voice interaction

Interactive Configuration:
- mDNS/Zeroconf discovery for Home Assistant instances
- OAuth2 authentication using HA's IndieAuth-style flow
- Feature selection and camera configuration

SAFE DOMAIN: Home automation only. Medical/health capabilities are prohibited.
"""

from .adapter import Adapter, HomeAssistantAdapter
from .communication_service import HACommunicationService
from .configurable import HAConfigurableAdapter
from .schemas import (
    CameraAnalysisResult,
    CameraFrame,
    CameraStatus,
    DetectionEvent,
    EventSubscription,
    EventType,
    HAAutomationResult,
    HADeviceState,
    HAEventType,
    HANotification,
)
from .service import HAIntegrationService
from .tool_service import HAToolService

__all__ = [
    # Adapter (for load_adapter() compatibility)
    "Adapter",
    "HomeAssistantAdapter",
    # Properly separated services (TOOL vs COMMUNICATION)
    "HAToolService",  # ServiceType.TOOL - device control, automations, sensors
    "HACommunicationService",  # ServiceType.COMMUNICATION - events, TTS, messaging
    # Legacy service (shared by tool and comms)
    "HAIntegrationService",
    # Configurable adapter
    "HAConfigurableAdapter",
    # Schemas
    "DetectionEvent",
    "CameraFrame",
    "CameraStatus",
    "CameraAnalysisResult",
    "HADeviceState",
    "HAAutomationResult",
    "HANotification",
    "EventSubscription",
    "EventType",
    "HAEventType",
]
