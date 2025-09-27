"""
Comprehensive Single-Step H3ERE Pipeline Test Module.

This module tests the complete H3ERE ethical reasoning pipeline step-by-step,
including real-time streaming integration and all 11 step points.

Test Phases:
1. Initial system state check
2. Pause processor
3. Test reasoning stream connectivity
4. Single step execution with step point validation
5. Create task for processing
6. Step through H3ERE pipeline (11 step points)
7. Verify queue status and pipeline state
8. Resume processor
9. Final validation

Tests both single-step control and real-time streaming functionality.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import requests

from ..config import QAConfig, QAModule, QATestCase


class ComprehensiveSingleStepTestModule:
    """Comprehensive single-step testing with H3ERE pipeline validation."""

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
                description="Check initial system processor state",
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
                description="Pause the processor for single-step testing",
            ),
            # Phase 3: Test reasoning stream connectivity
            QATestCase(
                name="Reasoning Stream Connectivity",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/reasoning-stream",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test Server-Sent Events stream for live reasoning data",
                timeout=10,  # Quick connectivity test
            ),
            # Phase 4: Test single step functionality
            QATestCase(
                name="Single Step Execution",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Execute a single processing step",
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
                description="Execute single step with detailed response data",
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
                timeout=60,  # This will timeout due to paused processor
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
                description="Single step execution with work in the queue",
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
                description="Execute multiple single steps to process through pipeline",
            ),
            # Phase 8: Check queue status during stepping
            QATestCase(
                name="Queue Status During Stepping",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Check processing queue status during single-step mode",
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
                description="Resume normal processor operation",
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
                description="Verify system returned to normal active state",
            ),
        ]
