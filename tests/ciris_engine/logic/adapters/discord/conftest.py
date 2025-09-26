"""Centralized fixtures for Discord adapter tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver


class MockDiscordAttachment:
    """Mock Discord attachment for testing."""

    def __init__(
        self,
        filename: str,
        content_type: str,
        size: int = 1000,
        url: str = "https://example.com/file"
    ):
        self.filename = filename
        self.content_type = content_type
        self.size = size
        self.url = url


class MockDiscordMessage:
    """Mock Discord message for testing."""

    def __init__(
        self,
        message_id: str = "123456789",
        content: str = "Test message",
        author_name: str = "TestUser",
        attachments: list = None,
        embeds: list = None,
        reference: object = None,
        channel: object = None
    ):
        self.id = message_id
        self.content = content
        self.author = MagicMock()
        self.author.display_name = author_name
        self.author.id = "user123"
        self.attachments = attachments or []
        self.embeds = embeds or []
        self.reference = reference
        self.channel = channel or MagicMock()


class MockDiscordReference:
    """Mock Discord message reference for replies."""

    def __init__(self, message_id: str, resolved: object = None):
        self.message_id = message_id
        self.resolved = resolved


@pytest.fixture
def mock_attachment():
    """Factory for creating mock attachments."""
    return MockDiscordAttachment


@pytest.fixture
def mock_message():
    """Factory for creating mock Discord messages."""
    return MockDiscordMessage


@pytest.fixture
def mock_reference():
    """Factory for creating mock Discord references."""
    return MockDiscordReference


@pytest.fixture
def discord_observer():
    """Create a Discord observer for testing with comprehensive mocking."""
    observer = DiscordObserver(
        agent_id="test_agent",
        monitored_channel_ids=["test_channel"],
        wa_user_ids=["wa_user"],
        deferral_channel_id="deferral_channel"
    )

    # Mock the vision helper and document parser
    observer._vision_helper = MagicMock()
    observer._vision_helper.is_available.return_value = True
    observer._vision_helper.process_image_attachments_list = AsyncMock(return_value="Image description")
    observer._vision_helper.process_embeds = AsyncMock(return_value="Embed description")

    observer._document_parser = MagicMock()
    observer._document_parser.is_available.return_value = True
    observer._document_parser.process_attachments = AsyncMock(return_value="Document text")

    # Mock document attachment detection to only accept PDF/DOCX
    def mock_is_document_attachment(attachment):
        return (hasattr(attachment, 'content_type') and
                attachment.content_type in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ])
    observer._document_parser._is_document_attachment.side_effect = mock_is_document_attachment

    # Mock additional services for comprehensive testing
    observer.adaptive_filter_service = MagicMock()
    observer.communication_service = MagicMock()
    observer.communication_service.send_message = AsyncMock()

    # Mock common async methods
    observer._create_priority_observation_result = AsyncMock()
    observer._create_passive_observation_result = AsyncMock()
    observer._add_to_feedback_queue = AsyncMock()
    # Don't mock _handle_priority_observation and _handle_passive_observation by default
    # Let individual tests decide if they want to mock or test the real methods

    return observer


@pytest.fixture
def sample_discord_message(mock_message):
    """Create a sample Discord message for testing."""
    return mock_message(
        message_id="msg123",
        content="Sample message content",
        author_name="TestUser"
    )


@pytest.fixture
def sample_discord_message_with_reply(mock_message, mock_reference):
    """Create a Discord message that's a reply for testing."""
    original = mock_message(
        message_id="original123",
        content="Original message",
        author_name="OriginalUser"
    )

    reference = mock_reference("original123", resolved=original)

    return mock_message(
        message_id="reply123",
        content="Reply message",
        author_name="ReplyUser",
        reference=reference
    )


@pytest.fixture
def priority_filter_result():
    """Create a priority filter result for testing."""
    result = MagicMock()
    result.action = "PRIORITY"
    result.priority.value = "high"
    result.triggered_filters = ["urgency", "keyword"]
    return result


@pytest.fixture
def passive_filter_result():
    """Create a passive filter result for testing."""
    result = MagicMock()
    result.action = "PASSIVE"
    result.priority.value = "low"
    result.triggered_filters = []
    return result


@pytest.fixture
def ignore_filter_result():
    """Create an ignore filter result for testing."""
    result = MagicMock()
    result.action = "IGNORE"
    result.priority.value = "none"
    result.triggered_filters = []
    return result


@pytest.fixture
def mock_discord_client():
    """Create a comprehensive mock Discord client for testing."""
    client = AsyncMock()

    # Mock basic client properties
    client.user = MagicMock()
    client.user.id = "bot123"
    client.user.display_name = "CIRIS Bot"

    # Mock guilds and channels
    mock_guild = AsyncMock()
    mock_guild.id = "guild123"
    mock_guild.name = "Test Guild"

    mock_channel = AsyncMock()
    mock_channel.id = "channel123"
    mock_channel.name = "test-channel"
    mock_channel.guild = mock_guild

    client.get_channel.return_value = mock_channel
    client.fetch_channel.return_value = mock_channel
    client.get_guild.return_value = mock_guild
    client.fetch_guild.return_value = mock_guild

    return client


@pytest.fixture
def mock_vision_helper():
    """Create a comprehensive mock vision helper for testing."""
    helper = MagicMock()
    helper.is_available.return_value = True
    helper.process_image_attachments_list = AsyncMock(return_value="Test image description")
    helper.process_embeds = AsyncMock(return_value="Test embed description")
    helper.process_image_attachments = AsyncMock(return_value="Single image description")
    return helper


@pytest.fixture
def mock_document_parser():
    """Create a comprehensive mock document parser for testing."""
    parser = MagicMock()
    parser.is_available.return_value = True
    parser.process_attachments = AsyncMock(return_value="Test document content")

    def mock_is_document_attachment(attachment):
        return (hasattr(attachment, 'content_type') and
                attachment.content_type in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ])
    parser._is_document_attachment.side_effect = mock_is_document_attachment
    return parser


@pytest.fixture
def mock_service_registry():
    """Create a mock service registry with common services."""
    registry = MagicMock()

    # Mock communication service
    comm_service = MagicMock()
    comm_service.send_message = AsyncMock()
    comm_service.edit_message = AsyncMock()
    comm_service.delete_message = AsyncMock()
    comm_service.add_reaction = AsyncMock()

    # Mock adaptive filter service
    filter_service = MagicMock()
    filter_service.filter_message = AsyncMock()

    # Mock memory service
    memory_service = MagicMock()
    memory_service.memorize_observation = AsyncMock()

    registry.get_service.side_effect = lambda name: {
        "communication": comm_service,
        "adaptive_filter": filter_service,
        "memory": memory_service
    }.get(name)

    return registry


@pytest.fixture
def sample_image_attachment(mock_attachment):
    """Create a sample image attachment for testing."""
    return mock_attachment(
        filename="test_image.png",
        content_type="image/png",
        size=500000,
        url="https://example.com/test_image.png"
    )


@pytest.fixture
def sample_document_attachment(mock_attachment):
    """Create a sample document attachment for testing."""
    return mock_attachment(
        filename="test_document.pdf",
        content_type="application/pdf",
        size=1000000,
        url="https://example.com/test_document.pdf"
    )


@pytest.fixture
def sample_discord_guild():
    """Create a sample Discord guild for testing."""
    guild = MagicMock()
    guild.id = "guild123"
    guild.name = "Test Guild"

    # Mock members
    member = MagicMock()
    member.id = "user123"
    member.display_name = "TestUser"
    member.roles = []

    guild.get_member.return_value = member
    guild.fetch_member = AsyncMock(return_value=member)

    return guild


@pytest.fixture
def enhanced_discord_observer(discord_observer, mock_service_registry, mock_vision_helper, mock_document_parser):
    """Enhanced Discord observer with all services mocked."""
    observer = discord_observer

    # Enhance with comprehensive service mocking
    observer.service_registry = mock_service_registry
    observer._vision_helper = mock_vision_helper
    observer._document_parser = mock_document_parser

    return observer