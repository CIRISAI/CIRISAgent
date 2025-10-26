"""
Simple Single-Step Test Module.

This module provides basic single-step functionality tests that are easy to debug
and validate the core pause/step/resume functionality works correctly.
"""

import time
from typing import Any, Dict, List, Optional

import requests

from ..config import QAConfig, QAModule, QATestCase


class SimpleSingleStepTestModule:
    """Simple single-step testing for basic functionality validation."""

    @staticmethod
    def get_simple_single_step_tests() -> List[QATestCase]:
        """Get simple single-step test cases."""
        return [
            # Test 1: Basic pause functionality
            QATestCase(
                name="Pause Processor",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/pause",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test basic processor pause functionality",
            ),
            # Test 2: Single step when paused (should work)
            QATestCase(
                name="Single Step When Paused",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test single step execution when processor is paused",
            ),
            # Test 3: Resume functionality
            QATestCase(
                name="Resume Processor",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/resume",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test processor resume functionality",
            ),
            # Test 4: Single step when NOT paused (should fail gracefully)
            QATestCase(
                name="Single Step When Active",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={},
                expected_status=200,  # Returns 200 but with success=false in data
                requires_auth=True,
                description="Test single step fails gracefully when processor is active",
            ),
            # CRITICAL: Cleanup - Force resume even if previous tests failed
            QATestCase(
                name="CLEANUP: Force Resume Processor",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/resume",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Emergency cleanup: ensure processor is always resumed",
            ),
        ]
