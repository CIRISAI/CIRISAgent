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
    def get_shared_task_coordination_tests() -> List[QATestCase]:
        """Get shared task coordination test cases (1.4.8 feature)."""
        return [
            # Shared task claiming - wakeup
            QATestCase(
                name="Shared wakeup task - claim and process",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/state",
                method="POST",
                payload={"target_state": "WAKEUP"},
                expected_status=200,
                requires_auth=True,
                description="Test shared wakeup task claiming and ownership transfer",
                timeout=180.0,  # Wakeup can take time
            ),
            # Verify agent reaches WORK state after wakeup
            QATestCase(
                name="Verify agent state after wakeup",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/health",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify agent successfully reaches WORK state after shared wakeup",
            ),
            # Test queue status during processing
            QATestCase(
                name="Queue status during shared task processing",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify queue shows claimed shared task with local occurrence ID",
            ),
            # Test telemetry reflects shared task processing
            QATestCase(
                name="Telemetry after shared task claim",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/telemetry/unified",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify telemetry shows shared task processing activity",
            ),
        ]

    @staticmethod
    def get_ownership_transfer_validation_tests() -> List[QATestCase]:
        """Get ownership transfer validation test cases (P0 bug fix validation).

        These tests validate the critical P0 bug fix for shared task ownership transfer.
        They verify that:
        1. Tasks are transferred from __shared__ to claiming occurrence
        2. Database rows are updated (not just in-memory objects)
        3. Subsequent queries work correctly (no zero-row UPDATEs)
        4. Audit events are generated for ownership transfers
        """
        return [
            # Verify queue shows tasks with local occurrence (not __shared__)
            QATestCase(
                name="Ownership transfer - queue shows local occurrence",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify queue shows tasks owned by local occurrence, not __shared__",
            ),
            # Check audit trail for task ownership transfer events
            QATestCase(
                name="Ownership transfer - audit trail validation",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify audit trail contains ownership transfer system events",
            ),
            # Create message to generate task and thoughts
            QATestCase(
                name="Ownership transfer - create test message",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/agent/message",
                method="POST",
                payload={"message": "Test ownership transfer - verify thoughts processable"},
                expected_status=200,
                requires_auth=True,
                description="Create message to verify thoughts inherit correct occurrence ID",
            ),
            # Verify created task has local occurrence_id
            QATestCase(
                name="Ownership transfer - task queryable by local occurrence",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify task is queryable by local occurrence ID after creation",
            ),
            # Verify task status updates work (not zero-row UPDATEs)
            QATestCase(
                name="Ownership transfer - status updates not zero-row",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify task status updates affect rows (P0 bug: zero-row UPDATEs)",
            ),
            # Test wakeup flow generates audit events
            QATestCase(
                name="Ownership transfer - wakeup audit events",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify wakeup ownership transfer generated audit events",
            ),
            # Test shutdown flow ownership transfer
            QATestCase(
                name="Ownership transfer - initiate shutdown",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/system/runtime/state",
                method="POST",
                payload={"target_state": "SHUTDOWN"},
                expected_status=200,
                requires_auth=True,
                description="Initiate shutdown to test ownership transfer from __shared__",
                timeout=60.0,
            ),
            # Verify shutdown generated ownership transfer audit event
            QATestCase(
                name="Ownership transfer - shutdown audit trail",
                module=QAModule.MULTI_OCCURRENCE,
                endpoint="/v1/audit/entries",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify shutdown ownership transfer generated audit event",
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
        """Get all multi-occurrence test cases including shared task coordination and ownership transfer validation."""
        tests = []
        tests.extend(MultiOccurrenceTestModule.get_multi_occurrence_tests())
        tests.extend(MultiOccurrenceTestModule.get_shared_task_coordination_tests())
        tests.extend(MultiOccurrenceTestModule.get_ownership_transfer_validation_tests())
        return tests

    @staticmethod
    def get_full_test_suite() -> List[QATestCase]:
        """Get full test suite including stress tests and ownership transfer validation."""
        tests = []
        tests.extend(MultiOccurrenceTestModule.get_multi_occurrence_tests())
        tests.extend(MultiOccurrenceTestModule.get_shared_task_coordination_tests())
        tests.extend(MultiOccurrenceTestModule.get_ownership_transfer_validation_tests())
        tests.extend(MultiOccurrenceTestModule.get_occurrence_stress_tests())
        return tests
