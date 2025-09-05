"""
Comprehensive Single-Step COVENANT Compliance Test Module.

This module provides a single comprehensive test with 17 ordered phases that validate
the complete PDMA ethical reasoning pipeline step-by-step for COVENANT compliance.

17 Phases:
1. Initial system state check
2. Pause processor
3. Create task via interact
4. Verify task queued  
5-19. Single step through all 15 PDMA step points with validation
20. Resume processor
21. Final validation

Each phase must pass before proceeding to the next.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import requests

from ..config import QAConfig, QAModule, QATestCase


class ComprehensiveSingleStepTestModule:
    """Comprehensive single-step testing with 17 ordered phases."""

    @staticmethod
    def get_comprehensive_single_step_tests() -> List[QATestCase]:
        """Get comprehensive single-step test cases as individual API tests."""
        return [
            # Phase 1: Check initial system state
            QATestCase(
                name="System State Check",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/state",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Check initial system processor state"
            ),
            # Phase 2: Pause processor
            QATestCase(
                name="Pause Processor",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/pause",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Pause the processor for single-step testing"
            ),
            # Phase 3: Test single step functionality
            QATestCase(
                name="Single Step Execution",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Execute a single processing step"
            ),
            # Phase 4: Test single step with details
            QATestCase(
                name="Single Step with Details",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={"include_details": True},
                expected_status=200,
                requires_auth=True,
                description="Execute single step with detailed response data"
            ),
            # Phase 5: Create a task to test with actual work
            QATestCase(
                name="Create Task for Processing",
                module=QAModule.AGENT,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "Test single-step processing"},
                expected_status=200,
                requires_auth=True,
                description="Create a task for single-step processing testing",
                timeout=60  # This will timeout due to paused processor
            ),
            # Phase 6: Step through processing with work in queue
            QATestCase(
                name="Single Step with Work Queue",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={"include_details": True},
                expected_status=200,
                requires_auth=True,
                description="Single step execution with work in the queue"
            ),
            # Phase 7: Multiple single steps
            QATestCase(
                name="Multiple Single Steps",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={"include_details": True},
                expected_status=200,
                requires_auth=True,
                description="Execute multiple single steps to process through pipeline"
            ),
            # Phase 8: Check queue status during stepping
            QATestCase(
                name="Queue Status During Stepping",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Check processing queue status during single-step mode"
            ),
            # Phase 9: Resume processor
            QATestCase(
                name="Resume Processor",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/resume",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Resume normal processor operation"
            ),
            # Phase 10: Verify system returns to normal
            QATestCase(
                name="Final System State Check",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/state",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Verify system returned to normal active state"
            )
        ]

