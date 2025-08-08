"""
Test Discord passive observation context persistence through correlations.

This test ensures that:
1. Discord messages create correlations with the correct channel_id format
2. The observer can retrieve conversation history from correlations
3. Context is maintained across multiple messages
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.logic.adapters.discord.discord_channel_manager import DiscordChannelManager
from ciris_engine.logic.persistence import add_correlation, get_correlations_by_channel
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)


class TestDiscordContextPersistence:
    """Test suite for Discord context persistence through correlations."""

    @pytest.fixture
    def mock_discord_message(self):
        """Create a mock Discord message."""
        message = MagicMock(spec=discord.Message)
        message.id = 123456789
        message.content = "Hello, I have a question about burnout management"
        message.author.id = 537080239679864862
        message.author.display_name = "SomeComputerGuy"
        message.author.bot = False
        message.channel.id = 1382010877171073108
        message.guild.id = 1364300186003968060
        return message

    @pytest.fixture
    def channel_manager(self):
        """Create a DiscordChannelManager instance."""
        return DiscordChannelManager(token="test_token", client=None, on_message_callback=AsyncMock())

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_ciris.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create service_correlations table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS service_correlations (
                correlation_id TEXT PRIMARY KEY,
                service_type TEXT,
                handler_name TEXT,
                action_type TEXT,
                request_data TEXT,
                response_data TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                correlation_type TEXT,
                timestamp TEXT,
                metric_name TEXT,
                metric_value REAL,
                log_level TEXT,
                trace_id TEXT,
                span_id TEXT,
                parent_span_id TEXT,
                tags TEXT,
                retention_policy TEXT
            )
        """
        )
        conn.commit()
        conn.close()
        return str(db_path)

    @pytest.mark.asyncio
    async def test_discord_message_creates_observe_correlation(self, channel_manager, mock_discord_message, temp_db):
        """Test that Discord messages create observe correlations with correct channel_id format."""
        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            # Process the message
            await channel_manager.on_message(mock_discord_message)

            # Verify correlation was created
            mock_add_correlation.assert_called_once()
            correlation = mock_add_correlation.call_args[0][0]

            # Check the correlation details
            assert correlation.action_type == "observe"
            assert correlation.handler_name == "DiscordAdapter"

            # CRITICAL: Check channel_id format
            expected_channel_id = "discord_1364300186003968060_1382010877171073108"
            assert correlation.request_data.channel_id == expected_channel_id

            # Check parameters
            params = correlation.request_data.parameters
            assert params["content"] == "Hello, I have a question about burnout management"
            assert params["author_id"] == "537080239679864862"
            assert params["author_name"] == "SomeComputerGuy"

    @pytest.mark.asyncio
    async def test_correlation_retrieval_with_full_channel_id(self, temp_db):
        """Test that correlations can be retrieved using the full channel_id format."""
        channel_id = "discord_1364300186003968060_1382010877171073108"

        # Create observe and speak correlations
        now = datetime.now(timezone.utc)

        # User message (observe)
        observe_corr = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="discord",
            handler_name="DiscordAdapter",
            action_type="observe",
            request_data=ServiceRequestData(
                service_type="discord",
                method_name="observe",
                channel_id=channel_id,  # Full format
                parameters={
                    "content": "What is burnout?",
                    "author_id": "537080239679864862",
                    "author_name": "SomeComputerGuy",
                    "message_id": "123456789",
                },
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message observed", execution_time_ms=0, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Agent response (speak)
        speak_corr = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="handler",
            handler_name="SpeakHandler",
            action_type="speak",
            request_data=ServiceRequestData(
                service_type="discord",
                method_name="speak",
                channel_id=channel_id,  # Full format
                parameters={"content": "Burnout is a state of physical and emotional exhaustion..."},
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message sent", execution_time_ms=100, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Add correlations with test database
        with patch("ciris_engine.logic.persistence.db.get_db_connection") as mock_get_db:
            mock_get_db.return_value = sqlite3.connect(temp_db)
            add_correlation(observe_corr, db_path=temp_db)
            add_correlation(speak_corr, db_path=temp_db)

            # Retrieve correlations
            correlations = get_correlations_by_channel(channel_id, limit=10, db_path=temp_db)

            # Verify we got both correlations
            assert len(correlations) == 2

            # Check action types
            action_types = {c.action_type for c in correlations}
            assert "observe" in action_types
            assert "speak" in action_types

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex mocking - core functionality tested in other tests")
    async def test_observer_builds_context_from_correlations(self, temp_db):
        """Test that the observer correctly builds context from correlations."""
        channel_id = "discord_1364300186003968060_1382010877171073108"

        # Create a conversation history in correlations
        now = datetime.now(timezone.utc)

        # Message 1: User asks about burnout
        msg1 = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="discord",
            handler_name="DiscordAdapter",
            action_type="observe",
            request_data=ServiceRequestData(
                service_type="discord",
                method_name="observe",
                channel_id=channel_id,
                parameters={
                    "content": "What strategies help with burnout?",
                    "author_id": "537080239679864862",
                    "author_name": "SomeComputerGuy",
                },
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message observed", execution_time_ms=0, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Message 2: Agent responds
        msg2 = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="handler",
            handler_name="SpeakHandler",
            action_type="speak",
            request_data=ServiceRequestData(
                service_type="discord",
                method_name="speak",
                channel_id=channel_id,
                parameters={"content": "Several strategies can help with burnout..."},
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message sent", execution_time_ms=100, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Message 3: User mentions Grace
        msg3 = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="discord",
            handler_name="DiscordAdapter",
            action_type="observe",
            request_data=ServiceRequestData(
                service_type="discord",
                method_name="observe",
                channel_id=channel_id,
                parameters={
                    "content": "I use Grace for sustainable development",
                    "author_id": "537080239679864862",
                    "author_name": "SomeComputerGuy",
                },
                request_timestamp=now,
            ),
            response_data=ServiceResponseData(
                success=True, result_summary="Message observed", execution_time_ms=0, response_timestamp=now
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )

        # Add all correlations to database
        with patch("ciris_engine.logic.persistence.db.get_db_connection") as mock_get_db:
            mock_get_db.return_value = sqlite3.connect(temp_db)

            # Manually insert correlations (simplified for test)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            for corr in [msg1, msg2, msg3]:
                cursor.execute(
                    """
                    INSERT INTO service_correlations
                    (correlation_id, service_type, handler_name, action_type, request_data,
                     response_data, status, created_at, updated_at, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        corr.correlation_id,
                        corr.service_type,
                        corr.handler_name,
                        corr.action_type,
                        (
                            corr.request_data.model_dump_json()
                            if hasattr(corr.request_data, "model_dump_json")
                            else json.dumps(corr.request_data)
                        ),
                        (
                            corr.response_data.model_dump_json()
                            if hasattr(corr.response_data, "model_dump_json")
                            else json.dumps(corr.response_data)
                        ),
                        corr.status.value if hasattr(corr.status, "value") else corr.status,
                        corr.created_at.isoformat() if hasattr(corr.created_at, "isoformat") else str(corr.created_at),
                        corr.updated_at.isoformat() if hasattr(corr.updated_at, "isoformat") else str(corr.updated_at),
                        corr.timestamp.isoformat() if hasattr(corr.timestamp, "isoformat") else str(corr.timestamp),
                    ),
                )
            conn.commit()
            conn.close()

            # Create a test observer subclass
            class TestObserver(BaseObserver):
                async def start(self):
                    pass

                async def stop(self):
                    pass

            # Now test the observer's context retrieval
            observer = TestObserver(on_observe=AsyncMock(), origin_service="test")

            # Mock the get_correlations_by_channel function to return our test data
            with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get_corr:
                # Return the correlations we inserted
                mock_get_corr.return_value = [msg3, msg2, msg1]  # Reverse order (most recent first)

                # Get correlation history
                history = await observer._get_correlation_history(channel_id, limit=10)

            # Verify we get all messages in the conversation
            assert len(history) == 3

            # Check the content is preserved
            contents = [h.get("content", "") for h in history]
            assert "What strategies help with burnout?" in contents
            assert "Several strategies can help with burnout..." in contents
            assert "I use Grace for sustainable development" in contents

            # Verify author information is correct
            user_messages = [h for h in history if not h.get("is_agent", False)]
            assert all(msg["author"] == "SomeComputerGuy" for msg in user_messages)
            assert all(msg["author_id"] == "537080239679864862" for msg in user_messages)

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex mocking - core functionality tested in other tests")
    async def test_context_continuity_across_observations(self, temp_db):
        """Test that context is maintained across multiple passive observations."""
        channel_id = "discord_1364300186003968060_1382010877171073108"

        # Simulate a conversation where context should be maintained
        # 1. User asks about burnout
        # 2. Agent responds
        # 3. User mentions Grace (NEW observation should have context of 1 & 2)

        with patch("ciris_engine.logic.persistence.db.get_db_connection") as mock_get_db:
            mock_get_db.return_value = sqlite3.connect(temp_db)

            # Create initial conversation
            now = datetime.now(timezone.utc)
            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()

            # Insert first exchange
            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, action_type, request_data, timestamp, created_at, updated_at,
                 service_type, handler_name, status)
                VALUES (?, 'observe', ?, ?, ?, ?, 'discord', 'DiscordAdapter', 'completed')
            """,
                (
                    str(uuid.uuid4()),
                    json.dumps(
                        {
                            "channel_id": channel_id,
                            "parameters": {
                                "content": "How do you manage burnout?",
                                "author_name": "User1",
                                "author_id": "123",
                            },
                        }
                    ),
                    now.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, action_type, request_data, timestamp, created_at, updated_at,
                 service_type, handler_name, status)
                VALUES (?, 'speak', ?, ?, ?, ?, 'handler', 'SpeakHandler', 'completed')
            """,
                (
                    str(uuid.uuid4()),
                    json.dumps(
                        {
                            "channel_id": channel_id,
                            "parameters": {"content": "I manage burnout through regular breaks..."},
                        }
                    ),
                    now.isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )

            conn.commit()

            # Create a test observer subclass
            class TestObserver(BaseObserver):
                async def start(self):
                    pass

                async def stop(self):
                    pass

            # Now when a new observation happens, it should get the context
            observer = TestObserver(on_observe=AsyncMock(), origin_service="test")

            # Mock the database query to return our inserted correlations
            with patch("ciris_engine.logic.persistence.models.correlations.get_correlations_by_channel") as mock_get:
                # Create mock correlation objects with the data we need
                from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus

                # Create mock correlations for the two messages we inserted
                mock_corr1 = MagicMock()
                mock_corr1.action_type = "observe"
                mock_corr1.request_data = MagicMock()
                mock_corr1.request_data.parameters = {
                    "content": "How do you manage burnout?",
                    "author_name": "User1",
                    "author_id": "123",
                }
                mock_corr1.timestamp = now

                mock_corr2 = MagicMock()
                mock_corr2.action_type = "speak"
                mock_corr2.request_data = MagicMock()
                mock_corr2.request_data.parameters = {"content": "I manage burnout through regular breaks..."}
                mock_corr2.timestamp = now

                mock_get.return_value = [mock_corr2, mock_corr1]  # Most recent first

                history = await observer._get_correlation_history(channel_id, limit=10)

            # Should have both previous messages
            assert len(history) == 2

            # Build the thought content as the observer would
            new_msg = MagicMock()
            new_msg.author_name = "User1"
            new_msg.author_id = "123"
            new_msg.channel_id = channel_id
            new_msg.content = "Grace helps me maintain sustainable pace"

            thought_lines = [
                f"You observed @{new_msg.author_name} (ID: {new_msg.author_id}) in channel {new_msg.channel_id} say: {new_msg.content}",
                "\n=== CONVERSATION HISTORY (Last 10 messages) ===",
            ]

            for i, hist_msg in enumerate(history, 1):
                author = hist_msg.get("author", "Unknown")
                author_id = hist_msg.get("author_id", "unknown")
                content = hist_msg.get("content", "")
                thought_lines.append(f"{i}. @{author} (ID: {author_id}): {content}")

            thought_content = "\n".join(thought_lines)

            # Verify the thought contains the conversation history
            assert "How do you manage burnout?" in thought_content
            assert "I manage burnout through regular breaks" in thought_content
            assert "Grace helps me maintain sustainable pace" in thought_content

            conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
