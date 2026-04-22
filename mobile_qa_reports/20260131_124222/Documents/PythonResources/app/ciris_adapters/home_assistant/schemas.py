"""
Pydantic schemas for Home Assistant integration.

Provides type-safe data structures for events, camera frames, and device states.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of events that can be detected."""

    PERSON = "person"
    VEHICLE = "vehicle"
    ANIMAL = "animal"
    PACKAGE = "package"
    MOTION = "motion"
    ACTIVITY = "activity"


class HAEventType(str, Enum):
    """Home Assistant camera event types."""

    CAMERA_PERSON = "camera_person"
    CAMERA_VEHICLE = "camera_vehicle"
    CAMERA_ANIMAL = "camera_animal"
    CAMERA_PACKAGE = "camera_package"
    CAMERA_MOTION = "camera_motion"
    CAMERA_ACTIVITY = "camera_activity"


class DetectionEvent(BaseModel):
    """Represents a detected event from camera analysis."""

    event_type: EventType = Field(..., description="Type of event detected")
    camera_name: str = Field(..., description="Name of the camera that detected the event")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the event was detected")
    zones: List[str] = Field(default_factory=list, description="Detection zones triggered")
    description: str = Field("", description="Human-readable description of the event")
    ha_event_type: HAEventType = Field(default=HAEventType.CAMERA_MOTION, description="HA event type mapping")

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


class CameraFrame(BaseModel):
    """Represents extracted camera frame data."""

    camera_name: str = Field(..., description="Name of the camera")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the frame was captured")
    width: int = Field(..., gt=0, description="Frame width in pixels")
    height: int = Field(..., gt=0, description="Frame height in pixels")
    channels: int = Field(default=3, description="Number of color channels")
    brightness: float = Field(default=0.0, ge=0.0, le=255.0, description="Average brightness")
    motion_detected: bool = Field(default=False, description="Whether motion was detected")
    frame_index: int = Field(default=0, ge=0, description="Index of this frame in sequence")

    class Config:
        """Pydantic configuration."""

        arbitrary_types_allowed = True


class CameraStatus(BaseModel):
    """Status of a camera."""

    camera_name: str = Field(..., description="Name of the camera")
    stream_url: str = Field(..., description="RTSP stream URL")
    is_online: bool = Field(default=False, description="Whether camera is accessible")
    last_check: Optional[datetime] = Field(default=None, description="Last status check time")


class CameraAnalysisResult(BaseModel):
    """Result of camera feed analysis."""

    camera_name: str = Field(..., description="Name of the analyzed camera")
    duration_seconds: int = Field(..., ge=0, description="Duration of analysis")
    frames_analyzed: int = Field(default=0, ge=0, description="Number of frames processed")
    motion_detected: bool = Field(default=False, description="Whether motion was detected")
    objects_detected: List[str] = Field(default_factory=list, description="Objects found in frames")
    average_brightness: float = Field(default=0.0, ge=0.0, description="Average frame brightness")
    error: Optional[str] = Field(default=None, description="Error message if analysis failed")


class HADeviceState(BaseModel):
    """Home Assistant device state."""

    entity_id: str = Field(..., description="Home Assistant entity ID")
    state: str = Field(..., description="Current state value")
    friendly_name: str = Field(default="", description="Human-readable name")
    last_changed: Optional[datetime] = Field(default=None, description="When state last changed")
    last_updated: Optional[datetime] = Field(default=None, description="When state was last updated")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Entity attributes")
    domain: str = Field(default="", description="Entity domain (light, switch, etc.)")


class HAAutomationResult(BaseModel):
    """Result of triggering a Home Assistant automation."""

    entity_id: str = Field(..., description="Entity that was triggered")
    action: str = Field(..., description="Action that was performed")
    success: bool = Field(..., description="Whether the action succeeded")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the action was performed")
    error: Optional[str] = Field(default=None, description="Error message if action failed")


class HANotification(BaseModel):
    """Home Assistant notification to send."""

    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message")
    target: Optional[str] = Field(default=None, description="Target device/service")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional notification data")


class EventSubscription(BaseModel):
    """Subscription to Home Assistant events."""

    event_types: List[EventType] = Field(default_factory=list, description="Event types to subscribe to")
    cameras: List[str] = Field(default_factory=list, description="Cameras to monitor (empty = all)")
    callback_url: Optional[str] = Field(default=None, description="Webhook URL for event delivery")
    sensitivity: float = Field(default=0.7, ge=0.0, le=1.0, description="Detection sensitivity")
