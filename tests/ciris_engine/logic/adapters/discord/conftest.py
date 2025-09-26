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


@pytest.fixture
def mock_discord_adapter():
    """Create a comprehensive mock Discord adapter for testing."""
    from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter

    adapter = MagicMock(spec=DiscordAdapter)

    # Mock basic properties
    adapter.agent_id = "test_agent"
    adapter.is_connected = True
    adapter.client = MagicMock()
    adapter.client.user = MagicMock()
    adapter.client.user.id = "bot123"

    # Mock common methods
    adapter.start = AsyncMock()
    adapter.stop = AsyncMock()
    adapter.send_message = AsyncMock()
    adapter.edit_message = AsyncMock()
    adapter.delete_message = AsyncMock()
    adapter.add_reaction = AsyncMock()
    adapter.get_capabilities = MagicMock()
    adapter.get_status = MagicMock()
    adapter.is_healthy = MagicMock(return_value=True)

    return adapter


@pytest.fixture
def mock_discord_tool_service():
    """Create a comprehensive mock Discord tool service based on ToolService protocol."""
    from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
    from ciris_engine.schemas.services.core import ServiceCapabilities
    from ciris_engine.schemas.runtime.enums import ServiceType
    import uuid

    service = MagicMock()

    # Protocol-compliant properties
    service._client = MagicMock()
    service._time_service = MagicMock()
    service._results = {}
    service._tool_executions = 0
    service._tool_failures = 0
    service._tools = {
        "discord_send_message": AsyncMock(),
        "discord_send_embed": AsyncMock(),
        "discord_delete_message": AsyncMock(),
        "discord_timeout_user": AsyncMock(),
        "discord_ban_user": AsyncMock(),
        "discord_kick_user": AsyncMock(),
        "discord_add_role": AsyncMock(),
        "discord_remove_role": AsyncMock(),
        "discord_get_user_info": AsyncMock(),
        "discord_get_channel_info": AsyncMock(),
        "discord_get_guild_moderators": AsyncMock(),
    }

    # Mock ToolService protocol methods
    async def mock_execute_tool(tool_name: str, parameters: dict) -> ToolExecutionResult:
        correlation_id = parameters.get("correlation_id", str(uuid.uuid4()))
        service._tool_executions += 1

        if tool_name not in service._tools:
            service._tool_failures += 1
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown Discord tool: {tool_name}",
                correlation_id=correlation_id,
            )

        # Simulate successful execution
        result = ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"mock_result": True},
            error=None,
            correlation_id=correlation_id,
        )
        service._results[correlation_id] = result
        return result

    async def mock_get_available_tools() -> List[str]:
        return list(service._tools.keys())

    async def mock_get_tool_info(tool_name: str) -> Optional[ToolInfo]:
        if tool_name not in service._tools:
            return None
        return ToolInfo(
            name=tool_name,
            description=f"Mock {tool_name} description",
            category="discord",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[]
            )
        )

    async def mock_list_tools() -> List[str]:
        return await mock_get_available_tools()

    async def mock_validate_parameters(tool_name: str, parameters: dict) -> bool:
        return tool_name in service._tools

    async def mock_get_tool_result(correlation_id: str) -> Optional[ToolExecutionResult]:
        return service._results.get(correlation_id)

    def mock_get_capabilities() -> ServiceCapabilities:
        return ServiceCapabilities(
            service_name="DiscordToolService",
            actions=["execute_tool", "get_available_tools", "get_tool_info", "list_tools", "validate_parameters"],
            version="1.0.0",
            metadata={"mock": True}
        )

    def mock_get_service_type() -> ServiceType:
        return ServiceType.TOOL

    # Assign mocked methods
    service.execute_tool = mock_execute_tool
    service.get_available_tools = mock_get_available_tools
    service.get_tool_info = mock_get_tool_info
    service.list_tools = mock_list_tools
    service.validate_parameters = mock_validate_parameters
    service.get_tool_result = mock_get_tool_result
    service.get_capabilities = mock_get_capabilities
    service.get_service_type = mock_get_service_type

    # Lifecycle methods
    service.start = MagicMock()
    service.stop = MagicMock()
    service.set_client = MagicMock()

    return service


@pytest.fixture
def mock_discord_guidance_handler():
    """Create a comprehensive mock Discord guidance handler for testing."""
    handler = MagicMock()

    # Mock handler properties
    handler.client = MagicMock()
    handler.memory_service = MagicMock()
    handler.wa_user_ids = ["wa_user_123"]
    handler.deferral_channel_id = "deferral_channel"

    # Mock common methods
    handler.is_registered_wa = AsyncMock(return_value=True)
    handler.check_discord_roles = AsyncMock(return_value="AUTHORITY")
    handler.fetch_guidance_from_channel = AsyncMock()
    handler.send_deferral_to_channel = AsyncMock()
    handler.resolve_channel = AsyncMock()

    return handler


@pytest.fixture
def comprehensive_mock_setup(
    mock_discord_client,
    mock_service_registry,
    mock_vision_helper,
    mock_document_parser,
    mock_discord_guidance_handler
):
    """Comprehensive mock setup for complex Discord tests."""
    return {
        "client": mock_discord_client,
        "service_registry": mock_service_registry,
        "vision_helper": mock_vision_helper,
        "document_parser": mock_document_parser,
        "guidance_handler": mock_discord_guidance_handler
    }


@pytest.fixture
def discord_error_scenarios():
    """Common Discord error scenarios for testing."""
    import discord

    return {
        "forbidden": discord.Forbidden(MagicMock(), "Insufficient permissions"),
        "not_found": discord.NotFound(MagicMock(), "Channel not found"),
        "rate_limited": discord.HTTPException(MagicMock(), "Rate limited"),
        "connection_error": ConnectionError("Connection failed"),
        "timeout_error": TimeoutError("Request timed out")
    }


@pytest.fixture
def sample_reply_chain(mock_message, mock_reference):
    """Create a sample reply chain for testing reply processing."""
    # Original message
    original = mock_message(
        message_id="original123",
        content="Original message content",
        author_name="OriginalUser"
    )

    # First reply
    reply1_ref = mock_reference("original123", resolved=original)
    reply1 = mock_message(
        message_id="reply1_123",
        content="First reply",
        author_name="ReplyUser1",
        reference=reply1_ref
    )

    # Second reply (reply to first reply)
    reply2_ref = mock_reference("reply1_123", resolved=reply1)
    reply2 = mock_message(
        message_id="reply2_123",
        content="Second reply",
        author_name="ReplyUser2",
        reference=reply2_ref
    )

    return {
        "original": original,
        "reply1": reply1,
        "reply2": reply2,
        "chain": [original, reply1, reply2]
    }


@pytest.fixture
def mock_attachment_collection(mock_attachment):
    """Create a collection of different attachment types for testing."""
    return {
        "image_png": mock_attachment("image.png", "image/png", 500000),
        "image_jpg": mock_attachment("photo.jpg", "image/jpeg", 750000),
        "document_pdf": mock_attachment("doc.pdf", "application/pdf", 1500000),
        "document_docx": mock_attachment("text.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 800000),
        "other_txt": mock_attachment("readme.txt", "text/plain", 5000),
        "large_image": mock_attachment("large.png", "image/png", 25000000),  # Too large
        "large_doc": mock_attachment("large.pdf", "application/pdf", 50000000)  # Too large
    }


@pytest.fixture(scope="session")
def discord_config_samples():
    """Sample Discord configurations for testing."""
    return {
        "minimal": {
            "agent_id": "test_agent",
            "token": "test_token",
            "monitored_channels": ["123456"]
        },
        "full": {
            "agent_id": "test_agent",
            "token": "test_token",
            "monitored_channels": ["123456", "789012"],
            "wa_user_ids": ["wa_user_1", "wa_user_2"],
            "deferral_channel_id": "deferral_123",
            "enable_vision": True,
            "enable_document_parsing": True
        }
    }