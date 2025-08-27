"""
Comprehensive unit tests for the enhanced thought manager.

Tests cover:
- Seed thought generation with observation handling
- Regex pattern safety (ReDoS prevention)
- Task description parsing
- Conversation history extraction
- Thought type determination
- Context enrichment
- Channel identification
- Author information extraction
- Error handling for malformed descriptions
- Performance with large inputs
"""

import re
import time
from datetime import datetime, timezone
from typing import List
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.processors.support.thought_manager_enhanced import generate_seed_thought_enhanced
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)


class MockThoughtManager:
    """Mock thought manager for testing enhanced function."""

    def __init__(self) -> None:
        self.time_service = Mock()
        self.time_service.now.return_value = datetime.now(timezone.utc)


# Test fixtures
@pytest.fixture
def mock_thought_manager() -> MockThoughtManager:
    """Create mock thought manager."""
    return MockThoughtManager()


@pytest.fixture
def observation_task() -> Task:
    """Create task with observation format."""
    return Task(
        task_id="task_obs_123",
        channel_id="discord_123_456",
        description="Respond to message from @TestUser (ID: user_789) in #general: 'Hello CIRIS, how are you?'",
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        priority=5,
        parent_task_id=None,
        context=None,
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


@pytest.fixture
def standard_task() -> Task:
    """Create standard non-observation task."""
    return Task(
        task_id="task_std_123",
        channel_id="api_localhost_8080",
        description="Explain Python list comprehensions",
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        priority=5,
        parent_task_id=None,
        context=None,
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


@pytest.fixture
def sample_correlations() -> List[ServiceCorrelation]:
    """Create sample correlations for conversation history."""

    now_timestamp = datetime.now(timezone.utc)

    return [
        ServiceCorrelation(
            correlation_id="corr_1",
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            service_type="handler",
            handler_name="SpeakHandler",
            action_type="speak",
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now_timestamp,
            updated_at=now_timestamp,
            timestamp=now_timestamp,
            request_data=ServiceRequestData(
                service_type="handler",
                method_name="speak",
                parameters={"content": "Hello! I'm doing well, thank you for asking."},
                request_timestamp=now_timestamp,
            ),
            response_data=ServiceResponseData(success=True, execution_time_ms=10.5, response_timestamp=now_timestamp),
        ),
        ServiceCorrelation(
            correlation_id="corr_2",
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            service_type="handler",
            handler_name="ObserveHandler",
            action_type="observe",
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now_timestamp,
            updated_at=now_timestamp,
            timestamp=now_timestamp,
            request_data=ServiceRequestData(
                service_type="handler",
                method_name="observe",
                parameters={
                    "author_name": "TestUser",
                    "author_id": "user_789",
                    "content": "Can you help me with Python?",
                },
                request_timestamp=now_timestamp,
            ),
            response_data=ServiceResponseData(success=True, execution_time_ms=5.2, response_timestamp=now_timestamp),
        ),
    ]


class TestThoughtManagerEnhanced:
    """Test suite for enhanced thought manager."""

    def test_observation_thought_generation(
        self, mock_thought_manager: MockThoughtManager, observation_task: Task
    ) -> None:
        """Test generation of observation thought from task description."""
        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = []

            # Generate thought
            thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)

            # Verify thought properties
            assert thought is not None
            assert thought.thought_type == ThoughtType.OBSERVATION
            assert thought.source_task_id == "task_obs_123"
            assert thought.channel_id == "discord_123_456"

            # Verify content formatting
            assert "You observed user @TestUser (ID: user_789)" in thought.content
            assert "Channel discord_123_456" in thought.content
            assert "Adapter discord" in thought.content
            assert "Hello CIRIS, how are you?" in thought.content
            assert "evaluate if you should respond" in thought.content.lower()

    def test_standard_thought_generation(self, mock_thought_manager: MockThoughtManager, standard_task: Task) -> None:
        """Test generation of standard thought from non-observation task."""
        # Generate thought
        thought = generate_seed_thought_enhanced(mock_thought_manager, standard_task, round_number=0)

        # Verify thought properties
        assert thought is not None
        assert thought.thought_type == ThoughtType.STANDARD
        assert thought.content == f"Initial seed thought for task: {standard_task.description}"

    def test_regex_redos_prevention(self, mock_thought_manager: MockThoughtManager) -> None:
        """Test that regex patterns are safe from ReDoS attacks."""
        # Create malicious input that would cause ReDoS with vulnerable regex
        malicious_description = (
            "Respond to message from @"
            + "A" * 1000
            + " (ID: "
            + "B" * 1000
            + ") in #"
            + "C" * 1000
            + ": '"
            + "D" * 1000
            + "'"
        )

        malicious_task = Task(
            task_id="task_mal_123",
            channel_id="test_channel",
            description=malicious_description,
            status=TaskStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            priority=5,
            parent_task_id=None,
            context=None,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        # Time the regex execution
        start_time = time.time()

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = []

            # Generate thought - should complete quickly
            thought = generate_seed_thought_enhanced(mock_thought_manager, malicious_task, round_number=1)

        end_time = time.time()
        execution_time = end_time - start_time

        # Should complete in reasonable time (not exponential)
        assert execution_time < 1.0  # Should be much faster, but allowing margin
        assert thought is not None

    def test_conversation_history_integration(
        self,
        mock_thought_manager: MockThoughtManager,
        observation_task: Task,
        sample_correlations: List[ServiceCorrelation],
    ) -> None:
        """Test integration of conversation history."""
        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = sample_correlations

            # Generate thought
            thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)

            # Verify conversation history is included
            assert "CONVERSATION HISTORY" in thought.content
            assert "@CIRIS (ID: ciris): Hello! I'm doing well" in thought.content
            assert "@TestUser (ID: user_789): Can you help me with Python?" in thought.content

    def test_malformed_task_description(self, mock_thought_manager: MockThoughtManager) -> None:
        """Test handling of malformed task descriptions."""
        malformed_descriptions = [
            "Respond to message from @User in #channel: 'test'",  # Missing ID
            "Respond to message from User (ID: 123) in channel: 'test'",  # Missing @ and #
            "Random task description without pattern",  # No pattern match
            "",  # Empty description
            "Respond to message from @User (ID: ) in #: ''",  # Empty captures
        ]

        for desc in malformed_descriptions:
            task = Task(
                task_id=f"task_{desc[:10]}",
                channel_id="test_channel",
                description=desc,
                status=TaskStatus.ACTIVE,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                priority=5,
                parent_task_id=None,
                context=None,
                outcome=None,
                signed_by=None,
                signature=None,
                signed_at=None,
            )

            # Should handle gracefully
            thought = generate_seed_thought_enhanced(mock_thought_manager, task, round_number=1)

            assert thought is not None
            # Should fall back to standard thought
            if "Respond to message from" not in desc or not re.match(
                r"Respond to message from @(.*?) \(ID: (.*?)\) in #(.*?): '(.*?)'$", desc
            ):
                assert thought.thought_type == ThoughtType.STANDARD

    def test_special_characters_in_content(self, mock_thought_manager: MockThoughtManager) -> None:
        """Test handling of special characters in message content."""
        special_contents = [
            "Hello! How's it going? 😊",
            "Check this code: `print('hello')`",
            "Price is $100.50 (on sale!)",
            "Email: test@example.com",
            "Path: C:\\Users\\Test\\file.txt",
            'Quote: "To be or not to be"',
            "Math: 2+2=4, 3*3=9",
        ]

        for content in special_contents:
            task = Task(
                task_id=f"task_spec_{content[:5]}",
                channel_id="test_channel",
                description=f"Respond to message from @User (ID: 123) in #general: '{content}'",
                status=TaskStatus.ACTIVE,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                priority=5,
                parent_task_id=None,
                context=None,
                outcome=None,
                signed_by=None,
                signature=None,
                signed_at=None,
            )

            with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
                mock_get_corr.return_value = []

                # Generate thought
                thought = generate_seed_thought_enhanced(mock_thought_manager, task, round_number=1)

                # Verify content is preserved
                assert content in thought.content

    def test_channel_adapter_extraction(self, mock_thought_manager: MockThoughtManager) -> None:
        """Test extraction of adapter type from channel ID."""
        channel_tests = [
            ("discord_123_456", "discord"),
            ("api_localhost_8080", "api"),
            ("cli_terminal_1", "cli"),
            ("unknown_format", "unknown"),
            ("test", "unknown"),
        ]

        for channel_id, expected_adapter in channel_tests:
            task = Task(
                task_id=f"task_{channel_id}",
                channel_id=channel_id,
                description="Respond to message from @User (ID: 123) in #general: 'test'",
                status=TaskStatus.ACTIVE,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                priority=5,
                parent_task_id=None,
                context=None,
                outcome=None,
                signed_by=None,
                signature=None,
                signed_at=None,
            )

            with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
                mock_get_corr.return_value = []

                # Generate thought
                thought = generate_seed_thought_enhanced(mock_thought_manager, task, round_number=1)

                # Verify adapter extraction
                assert f"Adapter {expected_adapter}" in thought.content

    def test_round_number_handling(self, mock_thought_manager: MockThoughtManager, observation_task: Task) -> None:
        """Test handling of different round numbers."""
        round_numbers = [0, 1, 5, 10]

        for round_num in round_numbers:
            with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
                mock_get_corr.return_value = []

                # Generate thought
                thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=round_num)

                # Verify round number is set
                assert thought.round_number == round_num

    def test_thought_id_generation(self, mock_thought_manager: MockThoughtManager, observation_task: Task) -> None:
        """Test unique thought ID generation."""
        thoughts = []

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = []

            # Generate multiple thoughts
            for _ in range(5):
                thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)
                thoughts.append(thought)

        # Verify all thought IDs are unique
        thought_ids = [t.thought_id for t in thoughts]
        assert len(thought_ids) == len(set(thought_ids))

        # Verify ID format
        for thought in thoughts:
            assert thought.thought_id.startswith("th_seed_task_obs_123_")

    def test_empty_conversation_history(self, mock_thought_manager: MockThoughtManager, observation_task: Task) -> None:
        """Test handling when no conversation history exists."""
        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = []

            # Generate thought
            thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)

            # Should still include history section but indicate it's empty
            assert "CONVERSATION HISTORY (Last 0 messages)" in thought.content

    def test_correlation_attribute_handling(
        self, mock_thought_manager: MockThoughtManager, observation_task: Task
    ) -> None:
        """Test safe handling of correlation attributes."""
        # Create correlations with missing attributes
        now_timestamp = datetime.now(timezone.utc)

        incomplete_correlations = [
            ServiceCorrelation(
                correlation_id="corr_1",
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                service_type="handler",
                handler_name="SpeakHandler",
                action_type="speak",
                status=ServiceCorrelationStatus.COMPLETED,
                created_at=now_timestamp,
                updated_at=now_timestamp,
                timestamp=now_timestamp,
                request_data=None,  # Missing request_data
                response_data=ServiceResponseData(
                    success=True, execution_time_ms=10.5, response_timestamp=now_timestamp
                ),
            ),
            ServiceCorrelation(
                correlation_id="corr_2",
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                service_type="handler",
                handler_name="ObserveHandler",
                action_type="observe",
                status=ServiceCorrelationStatus.COMPLETED,
                created_at=now_timestamp,
                updated_at=now_timestamp,
                timestamp=now_timestamp,
                request_data=ServiceRequestData(
                    service_type="handler",
                    method_name="observe",
                    parameters={},  # Empty parameters
                    request_timestamp=now_timestamp,
                ),
                response_data=ServiceResponseData(
                    success=True, execution_time_ms=5.2, response_timestamp=now_timestamp
                ),
            ),
        ]

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = incomplete_correlations

            # Should handle gracefully without crashing
            thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)

            assert thought is not None

    def test_performance_with_large_history(
        self, mock_thought_manager: MockThoughtManager, observation_task: Task
    ) -> None:
        """Test performance with large conversation history."""
        # Create large history
        now_timestamp = datetime.now(timezone.utc)
        large_history = []

        for i in range(100):
            is_speak = i % 2 == 0
            large_history.append(
                ServiceCorrelation(
                    correlation_id=f"corr_{i}",
                    correlation_type=CorrelationType.SERVICE_INTERACTION,
                    service_type="handler",
                    handler_name="SpeakHandler" if is_speak else "ObserveHandler",
                    action_type="speak" if is_speak else "observe",
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=now_timestamp,
                    updated_at=now_timestamp,
                    timestamp=now_timestamp,
                    request_data=ServiceRequestData(
                        service_type="handler",
                        method_name="speak" if is_speak else "observe",
                        parameters={"content": f"Message {i}", "author_name": f"User{i}", "author_id": f"user_{i}"},
                        request_timestamp=now_timestamp,
                    ),
                    response_data=ServiceResponseData(
                        success=True, execution_time_ms=5.0, response_timestamp=now_timestamp
                    ),
                )
            )

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
            mock_get_corr.return_value = large_history[:20]  # Return 20 messages now

            start_time = time.time()

            # Generate thought
            thought = generate_seed_thought_enhanced(mock_thought_manager, observation_task, round_number=1)

            end_time = time.time()
            execution_time = end_time - start_time

            # Should complete quickly even with large history
            assert execution_time < 0.1
            assert thought is not None
            assert "CONVERSATION HISTORY (Last 20 messages)" in thought.content
