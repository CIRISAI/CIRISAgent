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

SAFE DOMAIN: Home automation only. Medical/health capabilities are prohibited.
"""

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

__all__ = [
    "HAIntegrationService",
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
