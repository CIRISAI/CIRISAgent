"""Platform capability schemas for CIRIS."""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class PlatformRequirement(str, Enum):
    """Requirements that a platform may or may not satisfy."""

    ANDROID_PLAY_INTEGRITY = "android_play_integrity"
    GOOGLE_NATIVE_AUTH = "google_native_auth"
    ANDROID_KEYSTORE = "android_keystore"


class PlatformCapabilities(BaseModel):
    """Detected platform capabilities."""

    platform: str = Field(default="unknown", description="Platform identifier")
    is_android: bool = Field(default=False, description="Whether running on Android")
    google_native_auth_available: bool = Field(
        default=False, description="Whether Google native auth is available"
    )
    play_integrity_available: bool = Field(
        default=False, description="Whether Play Integrity API is available"
    )
    keystore_available: bool = Field(
        default=False, description="Whether Android Keystore is available"
    )

    def satisfies(self, requirements: List[PlatformRequirement]) -> bool:
        """Check if this platform satisfies all given requirements."""
        for req in requirements:
            if req == PlatformRequirement.ANDROID_PLAY_INTEGRITY:
                if not self.play_integrity_available:
                    return False
            elif req == PlatformRequirement.GOOGLE_NATIVE_AUTH:
                if not self.google_native_auth_available:
                    return False
            elif req == PlatformRequirement.ANDROID_KEYSTORE:
                if not self.keystore_available:
                    return False
        return True
