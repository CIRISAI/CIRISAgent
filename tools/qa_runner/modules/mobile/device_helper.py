"""
Cross-Platform Device Helper Protocol

Abstract base class for device interaction across Android and iOS platforms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Platform(Enum):
    """Mobile platform types."""
    ANDROID = "android"
    IOS = "ios"
    UNKNOWN = "unknown"


@dataclass
class DeviceInfo:
    """Cross-platform device information."""
    identifier: str  # Serial (Android) or UDID (iOS)
    state: str  # "device", "booted", "offline", "shutdown"
    platform: Platform
    name: Optional[str] = None
    os_version: Optional[str] = None
    model: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """Check if device is ready for use."""
        return self.state in ("device", "booted")


@dataclass
class UIElement:
    """Cross-platform UI element representation."""
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    class_name: str = ""
    bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)  # left, top, right, bottom
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    checkable: bool = False
    checked: bool = False
    scrollable: bool = False
    package: str = ""

    # Platform-specific attributes
    platform_attrs: Dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of element."""
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)

    @property
    def width(self) -> int:
        """Get element width."""
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        """Get element height."""
        return self.bounds[3] - self.bounds[1]


@dataclass
class LogCollection:
    """Results from log collection."""
    output_dir: Path
    app_logs: List[Path] = field(default_factory=list)
    system_logs: List[Path] = field(default_factory=list)
    crash_logs: List[Path] = field(default_factory=list)
    databases: List[Path] = field(default_factory=list)
    preferences: List[Path] = field(default_factory=list)
    screenshots: List[Path] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeviceHelper(ABC):
    """
    Abstract base class for device interaction.

    Provides a unified interface for Android (ADB) and iOS (xcrun/idevice) operations.
    """

    platform: Platform = Platform.UNKNOWN

    # ========== Device Management ==========

    @abstractmethod
    def get_devices(self) -> List[DeviceInfo]:
        """Get list of connected/available devices."""
        pass

    @abstractmethod
    def is_device_connected(self) -> bool:
        """Check if target device is connected and ready."""
        pass

    @abstractmethod
    def wait_for_device(self, timeout: int = 60) -> bool:
        """Wait for device to become available."""
        pass

    # ========== App Management ==========

    @abstractmethod
    def install_app(self, app_path: str, reinstall: bool = True) -> bool:
        """
        Install application on device.

        Args:
            app_path: Path to APK (Android) or .app/.ipa (iOS)
            reinstall: Whether to reinstall if already installed
        """
        pass

    @abstractmethod
    def uninstall_app(self, bundle_id: str) -> bool:
        """Uninstall application from device."""
        pass

    @abstractmethod
    def launch_app(self, bundle_id: str, activity: Optional[str] = None) -> bool:
        """
        Launch application.

        Args:
            bundle_id: Package name (Android) or Bundle ID (iOS)
            activity: Activity to launch (Android only, ignored on iOS)
        """
        pass

    @abstractmethod
    def force_stop_app(self, bundle_id: str) -> bool:
        """Force stop application."""
        pass

    @abstractmethod
    def clear_app_data(self, bundle_id: str) -> bool:
        """Clear application data/cache."""
        pass

    @abstractmethod
    def is_app_installed(self, bundle_id: str) -> bool:
        """Check if application is installed."""
        pass

    @abstractmethod
    def is_app_running(self, bundle_id: str) -> bool:
        """Check if application is currently running."""
        pass

    # ========== UI Interaction ==========

    @abstractmethod
    def tap(self, x: int, y: int) -> bool:
        """Tap at coordinates."""
        pass

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """Swipe from (x1,y1) to (x2,y2)."""
        pass

    @abstractmethod
    def input_text(self, text: str) -> bool:
        """Input text (requires focused text field)."""
        pass

    @abstractmethod
    def press_back(self) -> bool:
        """Press back button (Android) or swipe back gesture (iOS)."""
        pass

    @abstractmethod
    def press_home(self) -> bool:
        """Press home button."""
        pass

    @abstractmethod
    def press_enter(self) -> bool:
        """Press enter/return key."""
        pass

    # ========== Screen Capture ==========

    @abstractmethod
    def screenshot(self, output_path: str) -> bool:
        """Take screenshot and save to path."""
        pass

    @abstractmethod
    def get_screen_size(self) -> Tuple[int, int]:
        """Get screen dimensions (width, height)."""
        pass

    # ========== UI Hierarchy ==========

    @abstractmethod
    def dump_ui_hierarchy(self) -> str:
        """Dump UI hierarchy as XML/JSON string."""
        pass

    @abstractmethod
    def find_element_by_text(self, text: str, exact: bool = False) -> Optional[UIElement]:
        """Find UI element by text content."""
        pass

    @abstractmethod
    def find_element_by_id(self, resource_id: str) -> Optional[UIElement]:
        """Find UI element by resource ID."""
        pass

    @abstractmethod
    def find_elements_by_class(self, class_name: str) -> List[UIElement]:
        """Find all UI elements by class name."""
        pass

    # ========== Logging ==========

    @abstractmethod
    def pull_logs(self, output_dir: str, bundle_id: str) -> LogCollection:
        """
        Pull comprehensive logs from device.

        Collects:
        - Application logs
        - System logs (filtered for app)
        - Crash reports
        - Database files
        - Preferences/settings
        """
        pass

    @abstractmethod
    def clear_logs(self) -> bool:
        """Clear device logs."""
        pass

    @abstractmethod
    def start_log_capture(self, output_path: str, bundle_id: str) -> bool:
        """Start continuous log capture to file."""
        pass

    @abstractmethod
    def stop_log_capture(self) -> bool:
        """Stop continuous log capture."""
        pass

    # ========== Utilities ==========

    @abstractmethod
    def grant_permission(self, bundle_id: str, permission: str) -> bool:
        """Grant permission to app."""
        pass

    @abstractmethod
    def set_property(self, key: str, value: str) -> bool:
        """Set system property (if supported)."""
        pass

    @abstractmethod
    def get_property(self, key: str) -> Optional[str]:
        """Get system property."""
        pass

    @abstractmethod
    def forward_port(self, local_port: int, remote_port: int) -> bool:
        """Forward local port to device port."""
        pass


def detect_platform(app_path: str) -> Platform:
    """
    Detect platform from app path extension.

    Args:
        app_path: Path to app file

    Returns:
        Detected platform
    """
    path_lower = app_path.lower()
    if path_lower.endswith('.apk'):
        return Platform.ANDROID
    elif path_lower.endswith('.app') or path_lower.endswith('.ipa'):
        return Platform.IOS
    return Platform.UNKNOWN


def create_device_helper(
    platform: Platform,
    device_id: Optional[str] = None,
    **kwargs
) -> DeviceHelper:
    """
    Factory function to create appropriate device helper.

    Args:
        platform: Target platform
        device_id: Specific device ID (serial/UDID)
        **kwargs: Platform-specific options

    Returns:
        Platform-appropriate DeviceHelper instance
    """
    if platform == Platform.ANDROID:
        from .android.adb_helper import ADBDeviceHelper
        return ADBDeviceHelper(device_serial=device_id, **kwargs)
    elif platform == Platform.IOS:
        # Check if device_id indicates simulator
        if device_id and device_id.startswith('sim:'):
            from .ios.xcrun_helper import XCRunHelper
            return XCRunHelper(device_id=device_id[4:], **kwargs)
        else:
            from .ios.xcrun_helper import XCRunHelper
            # Default to simulator for now
            return XCRunHelper(device_id=device_id, **kwargs)
    else:
        raise ValueError(f"Unsupported platform: {platform}")
