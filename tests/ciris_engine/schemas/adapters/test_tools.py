"""
Unit tests for adapter tool schemas.

Tests the enhanced ToolInfo schema and related schemas for
skill-like rich documentation support.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.adapters.tools import (
    BinaryRequirement,
    ConfigRequirement,
    EnvVarRequirement,
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
    ToolResult,
    UsageExample,
)


class TestToolInfoBackwardCompatibility:
    """Test that existing ToolInfo usage continues to work."""

    def test_minimal_tool_info(self):
        """ToolInfo with only required fields works."""
        tool = ToolInfo(
            name="test_tool",
            description="A test tool",
            parameters=ToolParameterSchema(
                type="object",
                properties={"arg": {"type": "string"}},
                required=["arg"],
            ),
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.requirements is None
        assert tool.documentation is None
        assert tool.dma_guidance is None
        assert tool.tags == []
        assert tool.version is None
        assert tool.install_steps == []

    def test_tool_info_with_existing_fields(self):
        """ToolInfo with all existing fields works."""
        tool = ToolInfo(
            name="discord_send",
            description="Send a Discord message",
            parameters=ToolParameterSchema(
                type="object",
                properties={"channel_id": {"type": "string"}, "content": {"type": "string"}},
                required=["channel_id", "content"],
            ),
            category="communication",
            cost=0.01,
            when_to_use="When you need to send a message to Discord",
            context_enrichment=False,
            context_enrichment_params=None,
            platform_requirements=[],
            platform_requirements_rationale=None,
        )
        assert tool.category == "communication"
        assert tool.cost == 0.01
        assert tool.when_to_use == "When you need to send a message to Discord"


class TestBinaryRequirement:
    """Test BinaryRequirement schema."""

    def test_minimal(self):
        """BinaryRequirement with only name."""
        req = BinaryRequirement(name="ffmpeg")
        assert req.name == "ffmpeg"
        assert req.min_version is None
        assert req.verify_command is None

    def test_full(self):
        """BinaryRequirement with all fields."""
        req = BinaryRequirement(
            name="git",
            min_version="2.0.0",
            verify_command="git --version",
        )
        assert req.name == "git"
        assert req.min_version == "2.0.0"
        assert req.verify_command == "git --version"


class TestEnvVarRequirement:
    """Test EnvVarRequirement schema."""

    def test_minimal(self):
        """EnvVarRequirement with only name."""
        req = EnvVarRequirement(name="API_KEY")
        assert req.name == "API_KEY"
        assert req.description is None
        assert req.secret is False

    def test_secret(self):
        """EnvVarRequirement marked as secret."""
        req = EnvVarRequirement(
            name="OPENAI_API_KEY",
            description="OpenAI API key for LLM access",
            secret=True,
        )
        assert req.secret is True


class TestConfigRequirement:
    """Test ConfigRequirement schema."""

    def test_basic(self):
        """ConfigRequirement with key."""
        req = ConfigRequirement(key="adapters.home_assistant.token")
        assert req.key == "adapters.home_assistant.token"
        assert req.description is None


class TestToolRequirements:
    """Test ToolRequirements schema."""

    def test_empty(self):
        """ToolRequirements with defaults."""
        req = ToolRequirements()
        assert req.binaries == []
        assert req.any_binaries == []
        assert req.env_vars == []
        assert req.config_keys == []
        assert req.platforms == []

    def test_full(self):
        """ToolRequirements with all fields."""
        req = ToolRequirements(
            binaries=[BinaryRequirement(name="ffmpeg")],
            any_binaries=[
                BinaryRequirement(name="curl"),
                BinaryRequirement(name="wget"),
            ],
            env_vars=[EnvVarRequirement(name="API_KEY", secret=True)],
            config_keys=[ConfigRequirement(key="adapters.api.base_url")],
            platforms=["darwin", "linux"],
        )
        assert len(req.binaries) == 1
        assert len(req.any_binaries) == 2
        assert len(req.env_vars) == 1
        assert req.platforms == ["darwin", "linux"]


class TestInstallStep:
    """Test InstallStep schema."""

    def test_brew(self):
        """InstallStep for Homebrew."""
        step = InstallStep(
            id="brew-ffmpeg",
            kind="brew",
            label="Install ffmpeg via Homebrew",
            formula="ffmpeg",
            provides_binaries=["ffmpeg", "ffprobe"],
            platforms=["darwin"],
        )
        assert step.kind == "brew"
        assert step.formula == "ffmpeg"
        assert "ffmpeg" in step.provides_binaries

    def test_pip(self):
        """InstallStep for pip."""
        step = InstallStep(
            id="pip-requests",
            kind="pip",
            label="Install requests library",
            package="requests",
            verify_command="python -c 'import requests'",
        )
        assert step.kind == "pip"
        assert step.package == "requests"

    def test_manual(self):
        """InstallStep for manual installation."""
        step = InstallStep(
            id="manual-tool",
            kind="manual",
            label="Download and install manually",
            url="https://example.com/download",
            command="curl -L https://example.com/install.sh | bash",
        )
        assert step.kind == "manual"
        assert step.url is not None


class TestUsageExample:
    """Test UsageExample schema."""

    def test_basic(self):
        """UsageExample with required fields."""
        example = UsageExample(
            title="Get weather in San Francisco",
            code='{"latitude": 37.7749, "longitude": -122.4194}',
        )
        assert example.title == "Get weather in San Francisco"
        assert example.language == "json"

    def test_with_description(self):
        """UsageExample with description."""
        example = UsageExample(
            title="List files",
            description="Shows how to list files in a directory",
            code="ls -la /home",
            language="bash",
        )
        assert example.description is not None
        assert example.language == "bash"


class TestToolGotcha:
    """Test ToolGotcha schema."""

    def test_warning(self):
        """ToolGotcha with default warning severity."""
        gotcha = ToolGotcha(
            title="Rate limiting",
            description="API has a rate limit of 100 requests per minute",
        )
        assert gotcha.severity == "warning"

    def test_error(self):
        """ToolGotcha with error severity."""
        gotcha = ToolGotcha(
            title="Data loss risk",
            description="This operation cannot be undone",
            severity="error",
        )
        assert gotcha.severity == "error"


class TestToolDocumentation:
    """Test ToolDocumentation schema."""

    def test_empty(self):
        """ToolDocumentation with defaults."""
        docs = ToolDocumentation()
        assert docs.quick_start is None
        assert docs.examples == []
        assert docs.gotchas == []

    def test_full(self):
        """ToolDocumentation with all fields."""
        docs = ToolDocumentation(
            quick_start="Run `tool --help` to get started",
            detailed_instructions="## Usage\n\nThis tool does X, Y, Z...",
            examples=[
                UsageExample(title="Basic usage", code="tool run"),
            ],
            gotchas=[
                ToolGotcha(title="Timeout", description="Operations may timeout"),
            ],
            related_tools=["other_tool", "another_tool"],
            homepage="https://example.com",
            docs_url="https://docs.example.com",
        )
        assert docs.quick_start is not None
        assert len(docs.examples) == 1
        assert len(docs.gotchas) == 1
        assert len(docs.related_tools) == 2


class TestToolDMAGuidance:
    """Test ToolDMAGuidance schema."""

    def test_defaults(self):
        """ToolDMAGuidance with defaults."""
        guidance = ToolDMAGuidance()
        assert guidance.when_not_to_use is None
        assert guidance.ethical_considerations is None
        assert guidance.prerequisite_actions == []
        assert guidance.followup_actions == []
        assert guidance.min_confidence == 0.0
        assert guidance.requires_approval is False

    def test_requires_approval(self):
        """ToolDMAGuidance that requires approval."""
        guidance = ToolDMAGuidance(
            when_not_to_use="When user has not consented",
            ethical_considerations="This tool accesses sensitive data",
            requires_approval=True,
            min_confidence=0.8,
        )
        assert guidance.requires_approval is True
        assert guidance.min_confidence == 0.8

    def test_min_confidence_bounds(self):
        """min_confidence is bounded 0.0-1.0."""
        # Valid bounds
        ToolDMAGuidance(min_confidence=0.0)
        ToolDMAGuidance(min_confidence=1.0)
        ToolDMAGuidance(min_confidence=0.5)

        # Invalid: below 0
        with pytest.raises(ValidationError):
            ToolDMAGuidance(min_confidence=-0.1)

        # Invalid: above 1
        with pytest.raises(ValidationError):
            ToolDMAGuidance(min_confidence=1.1)


class TestToolInfoWithNewFields:
    """Test ToolInfo with all new fields populated."""

    def test_full_tool_info(self):
        """ToolInfo with all new fields."""
        tool = ToolInfo(
            name="weather:current",
            description="Get current weather conditions",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
                required=["latitude", "longitude"],
            ),
            category="weather",
            when_to_use="When you need current weather at a location",
            # New fields
            version="1.0.0",
            tags=["weather", "location", "api"],
            requirements=ToolRequirements(
                env_vars=[
                    EnvVarRequirement(name="WEATHER_API_KEY", secret=True),
                ],
                platforms=["darwin", "linux", "win32"],
            ),
            install_steps=[
                InstallStep(
                    id="pip-weather",
                    kind="pip",
                    label="Install weather library",
                    package="python-weather",
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Provide lat/lon to get weather",
                examples=[
                    UsageExample(
                        title="San Francisco weather",
                        code='{"latitude": 37.77, "longitude": -122.42}',
                    ),
                ],
                gotchas=[
                    ToolGotcha(
                        title="US only",
                        description="NOAA API only works for US locations",
                        severity="info",
                    ),
                ],
                homepage="https://weather.gov",
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="For medical weather advice",
                min_confidence=0.3,
            ),
        )

        assert tool.version == "1.0.0"
        assert "weather" in tool.tags
        assert tool.requirements is not None
        assert len(tool.requirements.env_vars) == 1
        assert len(tool.install_steps) == 1
        assert tool.documentation is not None
        assert tool.documentation.quick_start is not None
        assert tool.dma_guidance is not None
        assert tool.dma_guidance.min_confidence == 0.3

    def test_serialization_roundtrip(self):
        """ToolInfo serializes and deserializes correctly."""
        tool = ToolInfo(
            name="test",
            description="Test tool",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
            requirements=ToolRequirements(
                binaries=[BinaryRequirement(name="curl")],
            ),
            documentation=ToolDocumentation(
                quick_start="Just run it",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=True,
            ),
            tags=["test"],
            version="2.0",
        )

        # Serialize to dict
        data = tool.model_dump()

        # Deserialize back
        restored = ToolInfo.model_validate(data)

        assert restored.name == tool.name
        assert restored.requirements is not None
        assert restored.requirements.binaries[0].name == "curl"
        assert restored.documentation is not None
        assert restored.documentation.quick_start == "Just run it"
        assert restored.dma_guidance is not None
        assert restored.dma_guidance.requires_approval is True
        assert restored.tags == ["test"]
        assert restored.version == "2.0"


class TestExistingSchemas:
    """Ensure existing schemas still work."""

    def test_tool_result(self):
        """ToolResult works as before."""
        result = ToolResult(success=True, data={"value": 42})
        assert result.success is True
        assert result.data == {"value": 42}

    def test_tool_execution_result(self):
        """ToolExecutionResult works as before."""
        result = ToolExecutionResult(
            tool_name="test",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"result": "ok"},
            correlation_id="abc123",
        )
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.correlation_id == "abc123"
