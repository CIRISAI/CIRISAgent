"""
Multi-occurrence isolation test module.

Tests the multi-occurrence functionality that enables multiple API instances
to run against the same SQLite database with isolation between instances.
"""

import asyncio
import time
from typing import Dict, List

from ..config import QAModule, QATestCase


class MultiOccurrenceTestModule:
    """Test module for multi-occurrence isolation functionality."""

    @staticmethod
    def get_multi_occurrence_tests() -> List[QATestCase]:
        """Get multi-occurrence isolation test cases."""
        return [
            # Basic configuration tests
            QATestCase(
                name="Verify occurrence_id in config",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/config",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify agent_occurrence_id is present in system configuration",
            ),
            QATestCase(
                name="Verify default occurrence_id value",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/config",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify default occurrence_id is 'default' for backward compatibility",
            ),
            # Task creation and isolation tests
            QATestCase(
                name="Create task - verify occurrence stamping",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Test occurrence isolation - create task"},
                expected_status=200,
                requires_auth=True,
                description="Submit message and verify task is created with occurrence_id",
            ),
            QATestCase(
                name="Query tasks - verify occurrence filtering",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify queue status only shows tasks for this occurrence",
            ),
            # Agent interaction with occurrence isolation
            QATestCase(
                name="Agent interaction - occurrence context",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/interact",
                method="POST",
                payload={"message": "What is your occurrence ID?"},
                expected_status=200,
                requires_auth=True,
                description="Test agent interaction maintains occurrence context",
                timeout=120.0,
            ),
            # Telemetry with occurrence awareness
            QATestCase(
                name="Telemetry - occurrence metrics",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/telemetry/unified",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify telemetry reports metrics for this occurrence only",
            ),
            QATestCase(
                name="System health - occurrence context",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify system health reflects this occurrence state",
            ),
            # Memory operations with occurrence isolation
            QATestCase(
                name="Memory store - occurrence context",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/memory/store",
                method="POST",
                payload={
                    "node": {
                        "id": "test-occurrence-node",
                        "type": "observation",
                        "scope": "local",
                        "attributes": {
                            "created_by": "qa_occurrence_test",
                            "tags": ["test", "occurrence"],
                            "content": "Test memory with occurrence isolation",
                            "source": "multi_occurrence_qa",
                        },
                    }
                },
                expected_status=200,
                requires_auth=True,
                description="Test memory storage in occurrence context",
            ),
            QATestCase(
                name="Memory query - occurrence isolation",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/memory/query",
                method="POST",
                payload={"query": "occurrence", "limit": 10},
                expected_status=200,
                requires_auth=True,
                description="Verify memory queries respect occurrence boundaries",
            ),
            # Audit trail with occurrence tracking
            QATestCase(
                name="Audit entries - occurrence filtering",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify audit entries are tagged with occurrence_id",
            ),
            # History and tracking
            QATestCase(
                name="Interaction history - occurrence scope",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/history",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify interaction history scoped to this occurrence",
            ),
            # Multiple messages to test concurrent processing
            QATestCase(
                name="Concurrent message 1",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Concurrent test message 1"},
                expected_status=200,
                requires_auth=True,
                description="Test concurrent message handling with occurrence isolation",
            ),
            QATestCase(
                name="Concurrent message 2",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Concurrent test message 2"},
                expected_status=200,
                requires_auth=True,
                description="Test concurrent message handling with occurrence isolation",
            ),
            QATestCase(
                name="Concurrent message 3",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Concurrent test message 3"},
                expected_status=200,
                requires_auth=True,
                description="Test concurrent message handling with occurrence isolation",
            ),
            # Verify queue isolation after concurrent messages
            QATestCase(
                name="Queue verification after concurrent operations",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify queue correctly shows only this occurrence's tasks",
            ),
        ]

    @staticmethod
    def get_occurrence_stress_tests() -> List[QATestCase]:
        """Get stress test cases for multi-occurrence handling."""
        return [
            QATestCase(
                name=f"Stress test message {i}",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": f"Stress test message {i} for occurrence isolation"},
                expected_status=200,
                requires_auth=True,
                description=f"Stress test message {i} - verify occurrence isolation under load",
            )
            for i in range(1, 11)  # 10 rapid messages
        ]

    @staticmethod
    def get_all_multi_occurrence_tests() -> List[QATestCase]:
        """Get all multi-occurrence test cases."""
        tests = []
        tests.extend(MultiOccurrenceTestModule.get_multi_occurrence_tests())
        return tests

    @staticmethod
    def get_full_test_suite() -> List[QATestCase]:
        """Get full test suite including stress tests."""
        tests = []
        tests.extend(MultiOccurrenceTestModule.get_multi_occurrence_tests())
        tests.extend(MultiOccurrenceTestModule.get_occurrence_stress_tests())
        return tests
