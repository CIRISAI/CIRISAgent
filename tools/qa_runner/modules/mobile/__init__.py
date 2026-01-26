"""
Mobile QA Runner Module

Automated testing for the CIRIS mobile app using ADB and UI Automator.
Supports live testing with real Google accounts.
"""

from .adb_helper import ADBHelper
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

__all__ = [
    "ADBHelper",
    "UIAutomator",
    "MobileTestRunner",
    "test_app_launch",
    "test_google_signin",
    "test_local_login",
    "test_setup_wizard",
    "test_chat_interaction",
    "test_full_flow",
]
