"""Tests for the TSASPDMA (Tool-Specific Action Selection PDMA) Evaluator."""

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator, TSASPDMALLMResult
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams, ToolParams
from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolDocumentation,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    UsageExample,
)
from ciris_engine.schemas.runtime.enums import ThoughtType


def make_tool_info(name: str, description: str, **kwargs) -> ToolInfo:
    """Helper to create ToolInfo with default parameters."""
    if "parameters" not in kwargs:
        kwargs["parameters"] = ToolParameterSchema(type="object", properties={})
    return ToolInfo(name=name, description=description, **kwargs)


from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestTSASPDMALLMResult:
    """Tests for TSASPDMALLMResult model."""

    def test_tool_action_result(self) -> None:
        """Test creating a TOOL action result."""
        result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Tool is appropriate for this task",
            tool_parameters={"path": "/test"},
        )
        assert result.selected_action == HandlerActionType.TOOL
        assert result.tool_parameters == {"path": "/test"}

    def test_speak_action_result(self) -> None:
        """Test creating a SPEAK action result."""
        result = TSASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Need clarification",
            speak_content="What file would you like to read?",
        )
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.speak_content == "What file would you like to read?"

    def test_ponder_action_result(self) -> None:
        """Test creating a PONDER action result."""
        result = TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="Should reconsider approach",
            ponder_questions=["Is this the right tool?"],
        )
        assert result.selected_action == HandlerActionType.PONDER
        assert result.ponder_questions == ["Is this the right tool?"]

    def test_tool_action_with_corrected_name(self) -> None:
        """Test creating a TOOL action result with corrected tool_name."""
        result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Correcting tool name from ha_control_light to ha_device_control",
            tool_name="ha_device_control",  # Corrected name
            tool_parameters={"entity_id": "light.bedroom", "action": "turn_off"},
        )
        assert result.selected_action == HandlerActionType.TOOL
        assert result.tool_name == "ha_device_control"
        assert result.tool_parameters == {"entity_id": "light.bedroom", "action": "turn_off"}

    def test_tool_action_without_tool_name(self) -> None:
        """Test creating a TOOL action result without tool_name (normal mode)."""
        result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Tool is appropriate",
            tool_parameters={"path": "/test"},
        )
        assert result.selected_action == HandlerActionType.TOOL
        assert result.tool_name is None  # Not set in normal mode
        assert result.tool_parameters == {"path": "/test"}


class TestTSASPDMAEvaluator:
    """Tests for TSASPDMAEvaluator."""

    @pytest.fixture
    def mock_service_registry(self) -> MagicMock:
        """Create a mock service registry."""
        registry = MagicMock()
        registry.get_llm_service = MagicMock(return_value=AsyncMock())
        return registry

    @pytest.fixture
    def mock_sink(self) -> MagicMock:
        """Create a mock sink for events."""
        return MagicMock()

    @pytest.fixture
    def sample_tool_info(self) -> ToolInfo:
        """Create sample tool info for tests."""
        return ToolInfo(
            name="file_read",
            description="Read file contents",
            when_to_use="Use when you need to read a file's contents",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "File path to read"},
                },
                required=["path"],
            ),
            documentation=ToolDocumentation(
                quick_start="Use `file_read` with a path argument",
                detailed_instructions="This tool reads the contents of a file.",
                examples=[
                    UsageExample(
                        title="Read config",
                        description="Read a config file",
                        code='file_read(path="/etc/config")',
                        language="python",
                    )
                ],
                gotchas=[
                    ToolGotcha(
                        title="Binary files",
                        description="May not work well with binary files",
                        severity="warning",
                    )
                ],
            ),
            dma_guidance=ToolDMAGuidance(
                when_not_to_use="Don't use for binary files",
                ethical_considerations="Respect file permissions",
            ),
        )

    @pytest.fixture
    def sample_thought(self) -> ProcessingQueueItem:
        """Create sample thought item for tests."""
        return ProcessingQueueItem(
            thought_id="test-thought-123",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Please read the file at /tmp/test.txt"),
            source_task_id="test-task-456",
            thought_depth=0,
        )

    def test_convert_tool_result(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test converting TOOL action result."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Proceeding with tool",
            tool_parameters={"path": "/test"},
        )

        result = evaluator._convert_tsaspdma_result(llm_result, "file_read")

        assert result.selected_action == HandlerActionType.TOOL
        assert isinstance(result.action_parameters, ToolParams)
        assert result.action_parameters.name == "file_read"
        assert result.action_parameters.parameters == {"path": "/test"}

    def test_convert_tool_result_with_corrected_name(
        self, mock_service_registry: MagicMock, mock_sink: MagicMock
    ) -> None:
        """Test converting TOOL action result with corrected tool_name."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM returns corrected tool name
        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Correcting tool name",
            tool_name="ha_device_control",  # Corrected name
            tool_parameters={"entity_id": "light.bedroom", "action": "turn_off"},
        )

        # Original requested name was "ha_control_light"
        result = evaluator._convert_tsaspdma_result(llm_result, "ha_control_light")

        assert result.selected_action == HandlerActionType.TOOL
        assert isinstance(result.action_parameters, ToolParams)
        # Should use the corrected name from LLM, not the original
        assert result.action_parameters.name == "ha_device_control"
        assert result.action_parameters.parameters == {"entity_id": "light.bedroom", "action": "turn_off"}

    def test_convert_tool_result_without_correction(
        self, mock_service_registry: MagicMock, mock_sink: MagicMock
    ) -> None:
        """Test converting TOOL action result without tool_name correction (normal mode)."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM doesn't provide tool_name (normal mode)
        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Tool is appropriate",
            tool_parameters={"path": "/test"},
            # tool_name not set
        )

        result = evaluator._convert_tsaspdma_result(llm_result, "file_read")

        assert result.selected_action == HandlerActionType.TOOL
        assert isinstance(result.action_parameters, ToolParams)
        # Should use the original name when no correction
        assert result.action_parameters.name == "file_read"

    def test_convert_speak_result(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test converting SPEAK action result."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Need clarification",
            speak_content="Which file?",
        )

        result = evaluator._convert_tsaspdma_result(llm_result, "file_read")

        assert result.selected_action == HandlerActionType.SPEAK
        assert isinstance(result.action_parameters, SpeakParams)
        assert result.action_parameters.content == "Which file?"

    def test_convert_ponder_result(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test converting PONDER action result."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="Reconsidering",
            ponder_questions=["Is this the right tool?"],
        )

        result = evaluator._convert_tsaspdma_result(llm_result, "file_read")

        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)
        assert "Is this the right tool?" in result.action_parameters.questions

    def test_convert_unexpected_action_fallback(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test fallback for unexpected action types."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # Force an unexpected action
        llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.OBSERVE,  # Unexpected for TSASPDMA
            reasoning="Something went wrong",
        )

        result = evaluator._convert_tsaspdma_result(llm_result, "file_read")

        # Should fallback to PONDER
        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)

    def test_format_tool_documentation_basic(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test basic tool documentation formatting."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        tool = make_tool_info(
            name="test_tool",
            description="A test tool",
            when_to_use="Use for testing",
        )

        doc = evaluator._format_tool_documentation(tool)

        assert "test_tool" in doc
        assert "A test tool" in doc
        assert "Use for testing" in doc

    def test_format_tool_documentation_with_parameters(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
    ) -> None:
        """Test documentation formatting includes parameters."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        doc = evaluator._format_tool_documentation(sample_tool_info)

        assert "Parameter Schema" in doc
        assert "path" in doc
        assert "Required:" in doc

    def test_format_tool_documentation_with_examples(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
    ) -> None:
        """Test documentation formatting includes examples."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        doc = evaluator._format_tool_documentation(sample_tool_info)

        assert "Examples" in doc
        assert "Read config" in doc

    def test_format_tool_documentation_with_gotchas(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
    ) -> None:
        """Test documentation formatting includes gotchas."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        doc = evaluator._format_tool_documentation(sample_tool_info)

        assert "Gotchas" in doc
        assert "Binary files" in doc

    def test_format_tool_documentation_with_guidance(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
    ) -> None:
        """Test documentation formatting includes DMA guidance."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        doc = evaluator._format_tool_documentation(sample_tool_info)

        assert "DMA Guidance" in doc
        assert "When NOT to use" in doc
        assert "Ethical considerations" in doc

    def test_create_tsaspdma_messages(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
    ) -> None:
        """Test TSASPDMA message creation."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_template = MagicMock()
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.uses_accord_header.return_value = True
            mock_loader_instance.get_system_message.return_value = "System message"
            mock_loader_instance.get_user_message.return_value = "User message"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        messages = evaluator._create_tsaspdma_messages(
            tool_name="file_read",
            tool_info=sample_tool_info,
            aspdma_reasoning="ASPDMA selected this tool",
            original_thought_content="Read /tmp/test.txt",
        )

        # Should have accord, system, and user messages
        assert len(messages) >= 2
        roles = [m["role"] for m in messages]
        assert "system" in roles
        assert "user" in roles

    @pytest.mark.asyncio
    async def test_evaluate_tool_action_success(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test successful tool action evaluation."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader_instance.uses_accord_header.return_value = False
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader_instance.get_user_message.return_value = "User"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # Mock call_llm_structured
        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Tool appropriate for task",
            tool_parameters={"path": "/tmp/test.txt"},
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_action(
            tool_name="file_read",
            tool_info=sample_tool_info,
            aspdma_reasoning="ASPDMA selected file_read",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.TOOL
        assert isinstance(result.action_parameters, ToolParams)
        assert result.rationale.startswith("TSASPDMA:")

    @pytest.mark.asyncio
    async def test_evaluate_tool_action_returns_speak(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test evaluation returns SPEAK for clarification."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader_instance.uses_accord_header.return_value = False
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader_instance.get_user_message.return_value = "User"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Need to clarify file path",
            speak_content="Which file would you like me to read?",
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_action(
            tool_name="file_read",
            tool_info=sample_tool_info,
            aspdma_reasoning="ASPDMA selected file_read",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.SPEAK
        assert isinstance(result.action_parameters, SpeakParams)

    @pytest.mark.asyncio
    async def test_evaluate_tool_action_returns_ponder(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test evaluation returns PONDER to reconsider."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader_instance.uses_accord_header.return_value = False
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader_instance.get_user_message.return_value = "User"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="This tool is not appropriate",
            ponder_questions=["Should I use a different tool?"],
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_action(
            tool_name="file_read",
            tool_info=sample_tool_info,
            aspdma_reasoning="ASPDMA selected file_read",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)

    @pytest.mark.asyncio
    async def test_evaluate_tool_action_raises_on_error(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test evaluation raises on LLM error (no silent fallback)."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader_instance.uses_accord_header.return_value = False
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader_instance.get_user_message.return_value = "User"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        evaluator.call_llm_structured = AsyncMock(side_effect=RuntimeError("LLM error"))

        with pytest.raises(RuntimeError, match="LLM error"):
            await evaluator.evaluate_tool_action(
                tool_name="file_read",
                tool_info=sample_tool_info,
                aspdma_reasoning="ASPDMA selected file_read",
                original_thought=sample_thought,
            )

    @pytest.mark.asyncio
    async def test_evaluate_generic_interface(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        sample_tool_info: ToolInfo,
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test evaluate() generic interface."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader_instance.uses_accord_header.return_value = False
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader_instance.get_user_message.return_value = "User"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Proceeding",
            tool_parameters={"path": "/test"},
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate(
            tool_name="file_read",
            tool_info=sample_tool_info,
            aspdma_reasoning="Selected",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.TOOL

    @pytest.mark.asyncio
    async def test_evaluate_missing_required_args(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
    ) -> None:
        """Test evaluate() raises on missing required arguments."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.load_prompt_template.return_value = {}
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        with pytest.raises(ValueError, match="required"):
            await evaluator.evaluate()

    def test_repr(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test string representation."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
                model_name="test-model",
            )

        repr_str = repr(evaluator)
        assert "TSASPDMAEvaluator" in repr_str
        assert "test-model" in repr_str


class TestTSASPDMACorrectionMode:
    """Tests for TSASPDMA tool name correction mode."""

    @pytest.fixture
    def mock_service_registry(self) -> MagicMock:
        """Create a mock service registry."""
        registry = MagicMock()
        registry.get_llm_service = MagicMock(return_value=AsyncMock())
        return registry

    @pytest.fixture
    def mock_sink(self) -> MagicMock:
        """Create a mock sink for events."""
        return MagicMock()

    @pytest.fixture
    def available_tools(self) -> List[ToolInfo]:
        """Create a list of available tools for correction tests."""
        return [
            ToolInfo(
                name="ha_device_control",
                description="Control Home Assistant devices",
                when_to_use="Use to control lights, switches, and other HA devices",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "entity_id": {"type": "string", "description": "Entity ID"},
                        "action": {"type": "string", "description": "Action to perform"},
                    },
                    required=["entity_id", "action"],
                ),
            ),
            ToolInfo(
                name="file_read",
                description="Read file contents",
                when_to_use="Use when you need to read a file",
                parameters=ToolParameterSchema(type="object", properties={}),
            ),
            ToolInfo(
                name="web_search",
                description="Search the web",
                when_to_use="Use when you need to search for information online",
                parameters=ToolParameterSchema(type="object", properties={}),
            ),
        ]

    @pytest.fixture
    def sample_thought(self) -> ProcessingQueueItem:
        """Create sample thought item for tests."""
        return ProcessingQueueItem(
            thought_id="test-thought-correction",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="Turn off the bedroom light"),
            source_task_id="test-task-correction",
            thought_depth=0,
        )

    def test_format_available_tools_for_correction(
        self, mock_service_registry: MagicMock, mock_sink: MagicMock, available_tools: List[ToolInfo]
    ) -> None:
        """Test formatting available tools list for correction mode."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        result = evaluator._format_available_tools_for_correction(available_tools)

        # Should contain all tool names
        assert "ha_device_control" in result
        assert "file_read" in result
        assert "web_search" in result

        # Should contain descriptions
        assert "Control Home Assistant" in result
        assert "Read file contents" in result

        # Should contain when_to_use guidance
        assert "Use to control lights" in result

    def test_format_available_tools_empty_list(self, mock_service_registry: MagicMock, mock_sink: MagicMock) -> None:
        """Test formatting empty tools list."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader.return_value.load_prompt_template.return_value = {}
            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        result = evaluator._format_available_tools_for_correction([])
        assert "No tools available" in result

    @pytest.mark.asyncio
    async def test_evaluate_tool_correction_success(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        available_tools: List[ToolInfo],
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test successful tool correction - LLM finds the right tool."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_template = MagicMock()
            mock_template.get_prompt.return_value = "Tool correction template"
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.get_accord_mode.return_value = "none"
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM corrects ha_control_light -> ha_device_control
        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Correcting to ha_device_control which handles lights",
            tool_name="ha_device_control",
            tool_parameters={"entity_id": "light.bedroom", "action": "turn_off"},
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_correction(
            requested_tool_name="ha_control_light",  # Hallucinated name
            available_tools=available_tools,
            aspdma_reasoning="ASPDMA selected ha_control_light for turning off light",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.TOOL
        assert isinstance(result.action_parameters, ToolParams)
        assert result.action_parameters.name == "ha_device_control"
        assert result.action_parameters.parameters == {"entity_id": "light.bedroom", "action": "turn_off"}
        assert "TSASPDMA-CORRECTION" in result.rationale

    @pytest.mark.asyncio
    async def test_evaluate_tool_correction_returns_speak(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        available_tools: List[ToolInfo],
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test correction returns SPEAK when multiple tools could match."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_template = MagicMock()
            mock_template.get_prompt.return_value = ""
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.get_accord_mode.return_value = "none"
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM decides to ask for clarification
        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.SPEAK,
            reasoning="Multiple tools could match, need clarification",
            speak_content="Did you mean ha_device_control or file_read?",
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_correction(
            requested_tool_name="unknown_tool",
            available_tools=available_tools,
            aspdma_reasoning="ASPDMA selected unknown_tool",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.SPEAK
        assert isinstance(result.action_parameters, SpeakParams)
        assert "TSASPDMA-CORRECTION" in result.rationale

    @pytest.mark.asyncio
    async def test_evaluate_tool_correction_returns_ponder(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        available_tools: List[ToolInfo],
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test correction returns PONDER when no tool matches intent."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_template = MagicMock()
            mock_template.get_prompt.return_value = ""
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.get_accord_mode.return_value = "none"
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM decides no tool matches
        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.PONDER,
            reasoning="No available tool matches the user's intent",
            ponder_questions=["Should I use a different approach?"],
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_correction(
            requested_tool_name="nonexistent_tool",
            available_tools=available_tools,
            aspdma_reasoning="ASPDMA selected nonexistent_tool",
            original_thought=sample_thought,
        )

        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)
        assert "TSASPDMA-CORRECTION" in result.rationale

    @pytest.mark.asyncio
    async def test_evaluate_tool_correction_invalid_corrected_name(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        available_tools: List[ToolInfo],
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test correction falls back to PONDER if LLM returns invalid tool name."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_template = MagicMock()
            mock_template.get_prompt.return_value = ""
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.get_accord_mode.return_value = "none"
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        # LLM returns a tool_name that's also not in the available list
        mock_llm_result = TSASPDMALLMResult(
            selected_action=HandlerActionType.TOOL,
            reasoning="Trying to correct",
            tool_name="also_nonexistent",  # This is also not in available_tools
            tool_parameters={"some": "param"},
        )
        evaluator.call_llm_structured = AsyncMock(return_value=(mock_llm_result, None))

        result = await evaluator.evaluate_tool_correction(
            requested_tool_name="nonexistent_tool",
            available_tools=available_tools,
            aspdma_reasoning="ASPDMA selected nonexistent_tool",
            original_thought=sample_thought,
        )

        # Should fall back to PONDER since the corrected name is also invalid
        assert result.selected_action == HandlerActionType.PONDER
        assert isinstance(result.action_parameters, PonderParams)

    @pytest.mark.asyncio
    async def test_evaluate_tool_correction_raises_on_llm_error(
        self,
        mock_service_registry: MagicMock,
        mock_sink: MagicMock,
        available_tools: List[ToolInfo],
        sample_thought: ProcessingQueueItem,
    ) -> None:
        """Test correction raises on LLM error (no silent fallback)."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_template = MagicMock()
            mock_template.get_prompt.return_value = ""
            mock_loader_instance.load_prompt_template.return_value = mock_template
            mock_loader_instance.get_accord_mode.return_value = "none"
            mock_loader_instance.get_system_message.return_value = "System"
            mock_loader.return_value = mock_loader_instance

            evaluator = TSASPDMAEvaluator(
                service_registry=mock_service_registry,
                sink=mock_sink,
            )

        evaluator.call_llm_structured = AsyncMock(side_effect=RuntimeError("LLM error"))

        with pytest.raises(RuntimeError, match="LLM error"):
            await evaluator.evaluate_tool_correction(
                requested_tool_name="nonexistent_tool",
                available_tools=available_tools,
                aspdma_reasoning="ASPDMA selected nonexistent_tool",
                original_thought=sample_thought,
            )
