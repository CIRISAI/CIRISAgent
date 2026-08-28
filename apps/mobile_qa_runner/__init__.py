"""
Mobile QA Runner - Bridge for testing CIRIS on Android emulators.

This module provides a bridge between the main QA runner and the CIRIS
server running on an Android emulator. It handles:
- ADB port forwarding (emulator:8080 → localhost:8080)
- Device .env file management
- Mobile-specific test modules (setup wizard, service lights, etc.)

Usage:
    # From mobile/ directory
    python -m tools.mobile_qa_runner status      # Check emulator/server status
    python -m tools.mobile_qa_runner setup       # Create .env on device
    python -m tools.mobile_qa_runner bridge      # Start port forwarding
    python -m tools.mobile_qa_runner test auth   # Run auth tests via bridge

    # Or run the main QA runner through the bridge
    python -m tools.mobile_qa_runner run auth telemetry
"""

from .bridge import EmulatorBridge
from .config import MobileQAConfig

__all__ = ["EmulatorBridge", "MobileQAConfig"]
