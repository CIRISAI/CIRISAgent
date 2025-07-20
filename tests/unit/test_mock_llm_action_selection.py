"""
Unit tests for the Mock LLM action_selection function.

Tests cover:
- Basic functionality with empty/minimal inputs
- All 10 handler action types via forced_action
- Command parsing from user input
- Channel context handling (@channel: syntax)
- Follow-up thought processing
- Conversation history parsing
- Error cases and validation
- Parameter extraction and validation
"""

import pytest
from unittest.mock import patch, MagicMock
import json

from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.actions import (
    SpeakParams, MemorizeParams, RecallParams, PonderParams,
    ObserveParams, ToolParams, RejectParams, DeferParams,
    ForgetParams, TaskCompleteParams
)
from ciris_engine.schemas.services.graph_core import NodeType, GraphScope
from ciris_modular_services.mock_llm.responses_action_selection import action_selection


class TestActionSelectionBasics:
    """Test basic functionality of action_selection."""
    
    def test_empty_context_and_messages(self):
        """Test with no context or messages - should default to SPEAK."""
        result = action_selection(context=[], messages=[])
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND"
        assert "[MOCK LLM]" in result.rationale
    
    def test_none_context_and_messages(self):
        """Test with None context and messages."""
        result = action_selection(context=None, messages=None)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "[MOCKLLM DISCLAIMER] SPEAK IN RESPONSE TO TASK WITHOUT COMMAND"


class TestForcedActions:
    """Test all forced action handlers."""
    
    def test_forced_speak_action(self):
        """Test SPEAK action via forced_action."""
        context = ["forced_action:SPEAK", "action_params:Hello world!"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Hello world!"
        assert "Executing SPEAK action from mock command" in result.rationale
    
    def test_forced_speak_with_channel(self):
        """Test SPEAK with @channel: syntax."""
        context = ["forced_action:SPEAK", "action_params:@channel:discord_123 Cross-channel message"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Cross-channel message"
        assert hasattr(result.action_parameters, "channel_context")
        assert result.action_parameters.channel_context["channel_id"] == "discord_123"
    
    def test_forced_speak_context_display(self):
        """Test SPEAK with $context to display full context."""
        context = ["forced_action:SPEAK", "action_params:$context", "user_input:test", "task:sample"]
        messages = [{"role": "user", "content": "Test message"}]
        result = action_selection(context=context, messages=messages)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "Full Context Display" in result.action_parameters.content
        assert "user_input:test" in result.action_parameters.content
    
    def test_forced_memorize_action(self):
        """Test MEMORIZE action via forced_action."""
        context = ["forced_action:MEMORIZE", "action_params:test_node CONCEPT LOCAL"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.MEMORIZE
        assert result.action_parameters.node.id == "test_node"
        assert result.action_parameters.node.type.value == "CONCEPT"
        assert result.action_parameters.node.scope.value == "LOCAL"
    
    def test_forced_memorize_invalid_type(self):
        """Test MEMORIZE with invalid node type."""
        context = ["forced_action:MEMORIZE", "action_params:test_node INVALID LOCAL"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "Invalid node type" in result.action_parameters.content
        assert "AGENT, USER, CHANNEL, CONCEPT, CONFIG" in result.action_parameters.content
    
    def test_forced_recall_action(self):
        """Test RECALL action via forced_action."""
        context = ["forced_action:RECALL", "action_params:test query"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.RECALL
        assert result.action_parameters.query == "test query"
        assert result.action_parameters.limit == 10
    
    def test_forced_ponder_action(self):
        """Test PONDER action via forced_action."""
        context = ["forced_action:PONDER", "action_params:What should I do?; How can I help?"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.PONDER
        assert len(result.action_parameters.questions) == 2
        assert result.action_parameters.questions[0] == "What should I do?"
        assert result.action_parameters.questions[1] == "How can I help?"
    
    def test_forced_observe_action(self):
        """Test OBSERVE action via forced_action."""
        context = ["forced_action:OBSERVE", "action_params:discord_123 true"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.OBSERVE
        assert result.action_parameters.channel_context["channel_id"] == "discord_123"
        assert result.action_parameters.active is True
    
    def test_forced_tool_action(self):
        """Test TOOL action via forced_action."""
        context = ["forced_action:TOOL", "action_params:read_file {\"path\": \"/tmp/test.txt\"}"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.TOOL
        assert result.action_parameters.name == "read_file"
        assert result.action_parameters.parameters["path"] == "/tmp/test.txt"
    
    def test_forced_tool_curl_special_case(self):
        """Test TOOL action with curl special handling."""
        context = ["forced_action:TOOL", "action_params:curl https://example.com"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.TOOL
        assert result.action_parameters.name == "curl"
        assert result.action_parameters.parameters["url"] == "https://example.com"
    
    def test_forced_reject_action(self):
        """Test REJECT action via forced_action."""
        context = ["forced_action:REJECT", "action_params:This violates guidelines"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.REJECT
        assert result.action_parameters.reason == "This violates guidelines"
    
    def test_forced_defer_action(self):
        """Test DEFER action via forced_action."""
        context = ["forced_action:DEFER", "action_params:Need more context"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.DEFER
        assert result.action_parameters.reason == "Need more context"
        assert result.action_parameters.defer_until is None
    
    def test_forced_forget_action(self):
        """Test FORGET action via forced_action."""
        context = ["forced_action:FORGET", "action_params:user123 Privacy request"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.FORGET
        assert result.action_parameters.node.id == "user123"
        assert result.action_parameters.reason == "Privacy request"
    
    def test_forced_task_complete_action(self):
        """Test TASK_COMPLETE action via forced_action."""
        context = ["forced_action:TASK_COMPLETE"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.TASK_COMPLETE
        assert result.action_parameters.completion_reason == "Forced task completion via testing"


class TestCommandParsing:
    """Test command parsing from user input."""
    
    def test_user_input_speak_command(self):
        """Test $speak command from user_input."""
        context = ["user_input:$speak Hello from user input!"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Hello from user input!"
    
    def test_user_input_recall_command(self):
        """Test $recall command from user_input."""
        context = ["user_input:$recall weather"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.RECALL
        assert result.action_parameters.query == "weather"
        assert result.action_parameters.node_type.value == "CONCEPT"
    
    def test_user_input_memorize_command(self):
        """Test $memorize command from user_input."""
        context = ["user_input:$memorize The weather is sunny today"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.MEMORIZE
        assert result.action_parameters.node.id == "the_weather_is"
        assert hasattr(result.action_parameters.node.attributes, "tags")
    
    def test_user_speech_non_command(self):
        """Test non-command user input."""
        context = ["user_input:Hello, how are you?"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "SPEAK IN RESPONSE TO TASK WITHOUT COMMAND" in result.action_parameters.content


class TestMessageParsing:
    """Test parsing commands from messages."""
    
    def test_command_from_user_message(self):
        """Test extracting command from user message."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User @testuser said: $speak Hello from message!"}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Hello from message!"
    
    def test_api_format_command(self):
        """Test API format: @USERNAME (ID: USERNAME): command."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "@SYSTEM_ADMIN (ID: SYSTEM_ADMIN): $memorize test memory"}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.MEMORIZE
        assert result.action_parameters.node.id == "test_memory"
    
    def test_conversation_history_parsing(self):
        """Test extracting commands from conversation history."""
        messages = [
            {"role": "user", "content": """
=== CONVERSATION HISTORY ===
1. @USER (ID: USER): Hello
2. @AGENT (ID: AGENT): Hi there!
3. @SYSTEM_ADMIN (ID: SYSTEM_ADMIN): $memorize important fact
4. @USER (ID: USER): Thanks
"""}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.MEMORIZE
        assert result.action_parameters.node.id == "important_fact"


class TestFollowUpThoughts:
    """Test follow-up thought handling."""
    
    def test_speak_followup_thought(self):
        """Test follow-up from SPEAK handler."""
        messages = [
            {"role": "system", "content": "THOUGHT_TYPE=follow_up"},
            {"role": "user", "content": 'Original Thought: "Message sent successfully to channel discord_123"'}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.TASK_COMPLETE
        assert "SPEAK operation completed" in result.action_parameters.completion_reason
    
    def test_other_handler_followup(self):
        """Test follow-up from non-SPEAK handler."""
        messages = [
            {"role": "system", "content": "THOUGHT_TYPE=follow_up"},
            {"role": "user", "content": 'Original Thought: "CIRIS_FOLLOW_UP_THOUGHT: Found 5 memories about weather"'}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "Found 5 memories about weather" in result.action_parameters.content


class TestErrorCases:
    """Test error handling and edge cases."""
    
    def test_forced_action_no_params(self):
        """Test forced actions without required parameters."""
        context = ["forced_action:SPEAK"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "requires content" in result.action_parameters.content
    
    def test_invalid_forced_action(self):
        """Test invalid forced action type."""
        context = ["forced_action:INVALID_ACTION"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "Invalid action" in result.action_parameters.content
    
    def test_malformed_json_tool_params(self):
        """Test TOOL with malformed JSON parameters."""
        context = ["forced_action:TOOL", "action_params:test_tool key1=value1 key2=value2"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.TOOL
        assert result.action_parameters.name == "test_tool"
        assert result.action_parameters.parameters["key1"] == "value1"
        assert result.action_parameters.parameters["key2"] == "value2"


class TestHelp:
    """Test help command functionality."""
    
    def test_help_requested_context(self):
        """Test help via show_help_requested context."""
        context = ["show_help_requested"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "CIRIS Mock LLM Commands Help" in result.action_parameters.content
        assert "$speak" in result.action_parameters.content
        assert "$recall" in result.action_parameters.content
    
    def test_help_command(self):
        """Test $help command."""
        messages = [
            {"role": "user", "content": "$help"}
        ]
        result = action_selection(messages=messages)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert "CIRIS Mock LLM Commands Help" in result.action_parameters.content


class TestCustomRationale:
    """Test custom rationale functionality."""
    
    def test_custom_rationale(self):
        """Test custom rationale override."""
        context = [
            "forced_action:SPEAK",
            "action_params:Test message",
            "custom_rationale:Custom test rationale"
        ]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.rationale == "Custom test rationale"


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_empty_command_args(self):
        """Test commands with empty arguments."""
        context = ["user_input:$speak"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "[MOCK LLM] Hello!"
    
    def test_multiple_context_items(self):
        """Test with multiple context items of same type."""
        context = [
            "user_input:first input",
            "task:second input",
            "content:third input"
        ]
        result = action_selection(context=context)
        
        # Should use the first matching item
        assert result.selected_action == HandlerActionType.SPEAK
        assert "first input" in result.rationale
    
    def test_channel_only_speak(self):
        """Test @channel: with no content."""
        context = ["forced_action:SPEAK", "action_params:@channel:test_channel"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "[MOCK LLM] Cross-channel message"
        assert result.action_parameters.channel_context["channel_id"] == "test_channel"
    
    def test_recall_node_params(self):
        """Test RECALL with node_id, type, and scope."""
        context = ["forced_action:RECALL", "action_params:user123 USER LOCAL"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.RECALL
        assert result.action_parameters.node_id == "user123"
        assert result.action_parameters.node_type.value == "USER"
        assert result.action_parameters.scope.value == "LOCAL"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
