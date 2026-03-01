"""
Mobile QA Runner Module

Automated testing for the CIRIS mobile app.
Supports both Android (ADB) and iOS (xcrun simctl) platforms.
"""

# Legacy imports (backward compatibility)
from .adb_helper import ADBHelper

# Cross-platform device helper protocol
from .device_helper import (
    DeviceHelper,
    DeviceInfo,
    LogCollection,
    Platform,
    UIElement,
    create_device_helper,
    detect_platform,
)
from .test_cases import (
    test_app_launch,
    test_chat_interaction,
    test_full_flow,
    test_google_signin,
    test_local_login,
    test_setup_wizard,
)
from .test_runner import MobileTestRunner
from .ui_automator import UIAutomator

# Platform-specific helpers
try:
    from .android.adb_helper import ADBDeviceHelper
except ImportError:
    ADBDeviceHelper = None  # type: ignore

try:
    from .ios.xcrun_helper import XCRunHelper
except ImportError:
    XCRunHelper = None  # type: ignore

try:
    from .ios.ios_ui_automator import iOSUIAutomator
except ImportError:
    iOSUIAutomator = None  # type: ignore

# iOS test cases
try:
    from .ios_test_cases import (
        test_ios_app_launch,
        test_ios_connect_node,
        test_ios_connect_node_welcome,
        test_ios_full_flow,
        test_ios_local_login,
        test_ios_setup_wizard,
    )
except ImportError:
    pass

__all__ = [
    # Cross-platform
    "DeviceHelper",
    "DeviceInfo",
    "LogCollection",
    "Platform",
    "UIElement",
    "create_device_helper",
    "detect_platform",
    # Platform-specific
    "ADBDeviceHelper",
    "XCRunHelper",
    "iOSUIAutomator",
    # Legacy (backward compatibility)
    "ADBHelper",
    "UIAutomator",
    "MobileTestRunner",
    # Android test functions
    "test_app_launch",
    "test_google_signin",
    "test_local_login",
    "test_setup_wizard",
    "test_chat_interaction",
    "test_full_flow",
    # iOS test functions
    "test_ios_app_launch",
    "test_ios_local_login",
    "test_ios_setup_wizard",
    "test_ios_full_flow",
    "test_ios_connect_node",
    "test_ios_connect_node_welcome",
]
