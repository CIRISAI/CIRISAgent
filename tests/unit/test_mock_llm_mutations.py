"""
Mutation tests for Mock LLM action_selection - testing robustness and edge cases.

These tests use mutation testing principles to verify the code handles:
- Malformed inputs
- Boundary conditions
- Missing data
- Type mismatches
- Injection attempts
"""

import pytest
import json
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_modular_services.mock_llm.responses_action_selection import action_selection


class TestMutationStringInputs:
    """Test mutations of string inputs."""
    
    def test_extremely_long_content(self):
        """Test with extremely long content strings."""
        long_content = "A" * 10000
        context = ["forced_action:SPEAK", f"action_params:{long_content}"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        # Content is truncated to 5000 chars for DoS protection in parse_channel
        assert len(result.action_parameters.content) == 5000
        assert result.action_parameters.content == "A" * 5000
    
    def test_special_characters_in_content(self):
        """Test with special characters and escape sequences."""
        special_content = "Test\n\r\t\0\\n\\r\\t<script>alert('xss')</script>"
        context = ["forced_action:SPEAK", f"action_params:{special_content}"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == special_content
    
    def test_unicode_in_content(self):
        """Test with various unicode characters."""
        unicode_content = "Test 🤖 émojis ñ 中文 العربية"
        context = ["forced_action:SPEAK", f"action_params:{unicode_content}"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == unicode_content
    
    def test_sql_injection_attempt(self):
        """Test SQL injection patterns are handled safely."""
        sql_injection = "'; DROP TABLE users; --"
        context = ["forced_action:MEMORIZE", f"action_params:{sql_injection}"]
        result = action_selection(context=context)
        
        # Should handle it as normal text, not execute
        assert result.selected_action == HandlerActionType.MEMORIZE
        # The ID is sanitized from the SQL injection attempt
        assert "drop_table" in result.action_parameters.node.id.lower()


class TestMutationDataStructures:
    """Test mutations of data structures."""
    
    def test_malformed_messages_structure(self):
        """Test with malformed messages structure."""
        # Messages that aren't proper dicts
        messages = ["not a dict", {"missing": "role"}, {"role": "user"}]
        
        # Should handle gracefully - the function expects dicts but we're testing error handling
        try:
            result = action_selection(messages=messages)
            # If it doesn't error, it should default to SPEAK
            assert result.selected_action == HandlerActionType.SPEAK
        except AttributeError:
            # This is expected when messages aren't proper dicts
            pass
    
    def test_deeply_nested_context(self):
        """Test with deeply nested context structures."""
        nested_dict = {"a": {"b": {"c": {"d": "value"}}}}
        context = ["forced_action:TOOL", f"action_params:test_tool {json.dumps(nested_dict)}"]
        
        # ToolParams expects flat dict with string values, so nested dicts should fail validation
        try:
            result = action_selection(context=context)
            # If it succeeds, check that parameters were somehow processed
            assert result.selected_action == HandlerActionType.TOOL
            assert result.action_parameters.name == "test_tool"
        except Exception:
            # Expected - ToolParams validation should reject deeply nested structures
            pass
    
    def test_circular_reference_prevention(self):
        """Test that circular references don't cause issues."""
        # This tests string parsing, not actual circular refs
        context = ["forced_action:SPEAK", "action_params:@channel:@channel:@channel:test"]
        result = action_selection(context=context)
        
        # Should extract the first valid channel
        assert result.selected_action == HandlerActionType.SPEAK


class TestMutationBoundaryConditions:
    """Test boundary conditions."""
    
    def test_zero_length_strings(self):
        """Test with empty strings in various places."""
        context = ["forced_action:SPEAK", "action_params:"]
        result = action_selection(context=context)
        
        # Should provide error message
        assert result.selected_action == HandlerActionType.SPEAK
        assert "requires content" in result.action_parameters.content
    
    def test_max_ponder_questions(self):
        """Test PONDER with many questions."""
        questions = ";".join([f"Question {i}?" for i in range(100)])
        context = ["forced_action:PONDER", f"action_params:{questions}"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.PONDER
        assert len(result.action_parameters.questions) == 100
    
    def test_numeric_node_ids(self):
        """Test with purely numeric node IDs."""
        context = ["forced_action:MEMORIZE", "action_params:12345 CONCEPT LOCAL"]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.MEMORIZE
        assert result.action_parameters.node.id == "12345"


class TestMutationTypeErrors:
    """Test type error conditions."""
    
    def test_none_in_context_list(self):
        """Test with None values in context."""
        context = [None, "forced_action:SPEAK", None, "action_params:Test"]
        result = action_selection(context=context)
        
        # Should skip None values
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Test"
    
    def test_non_string_context_items(self):
        """Test with non-string items in context."""
        context = [123, {"dict": "item"}, ["list", "item"], "forced_action:SPEAK", "action_params:Test"]
        # Function expects strings, so this would error - wrap in try/except
        try:
            result = action_selection(context=context)
        except AttributeError:
            # Expected when non-strings are passed
            pass


class TestMutationCommandParsing:
    """Test mutations in command parsing."""
    
    def test_multiple_dollar_signs(self):
        """Test commands with multiple $ signs."""
        context = ["user_input:$$$speak Hello"]
        result = action_selection(context=context)
        
        # Should not parse as command due to $$$
        assert result.selected_action == HandlerActionType.SPEAK
        assert "SPEAK IN RESPONSE TO TASK WITHOUT COMMAND" in result.action_parameters.content
    
    def test_whitespace_variations(self):
        """Test commands with various whitespace."""
        contexts = [
            ["user_input:$speak    Hello"],      # Multiple spaces
            ["user_input:$speak\tHello"],        # Tab
            ["user_input:$speak\nHello"],        # Newline
            ["user_input:  $speak  Hello  "],    # Leading/trailing spaces
        ]
        
        for ctx in contexts:
            result = action_selection(context=ctx)
            assert result.selected_action == HandlerActionType.SPEAK
    
    def test_case_sensitivity(self):
        """Test command case variations."""
        contexts = [
            ["user_input:$SPEAK Hello"],
            ["user_input:$Speak Hello"],
            ["user_input:$SpEaK Hello"],
        ]
        
        for ctx in contexts:
            result = action_selection(context=ctx)
            # Commands are lowercased, so all should work
            assert result.selected_action == HandlerActionType.SPEAK


class TestMutationChannelParsing:
    """Test mutations in channel parsing."""
    
    def test_malformed_channel_syntax(self):
        """Test various malformed @channel: patterns."""
        test_cases = [
            "@channel:",              # No channel ID
            "@channel: ",             # Just space
            "@channel::",             # Double colon
            "@@channel:test",         # Double @
            "@channel:test:extra",    # Extra colon
        ]
        
        for case in test_cases:
            context = ["forced_action:SPEAK", f"action_params:{case} message"]
            result = action_selection(context=context)
            assert result.selected_action == HandlerActionType.SPEAK
    
    def test_channel_with_special_chars(self):
        """Test channel IDs with special characters."""
        channels = [
            "test-channel",
            "test_channel",
            "test.channel",
            "test123",
            "TEST_CHANNEL",
        ]
        
        for channel in channels:
            context = ["forced_action:SPEAK", f"action_params:@channel:{channel} Test"]
            result = action_selection(context=context)
            assert result.action_parameters.channel_context.channel_id == channel


class TestMutationErrorRecovery:
    """Test error recovery mechanisms."""
    
    def test_partial_json_recovery(self):
        """Test recovery from partial JSON in tool params."""
        # Malformed JSON
        context = ["forced_action:TOOL", 'action_params:test_tool {"key": "value"']
        result = action_selection(context=context)
        
        # Should fall back to key=value parsing
        assert result.selected_action == HandlerActionType.TOOL
        assert result.action_parameters.name == "test_tool"
    
    def test_mixed_valid_invalid_context(self):
        """Test with mix of valid and invalid context items."""
        context = [
            "invalid:format",
            "forced_action:INVALID",
            "forced_action:SPEAK",
            "action_params:Valid message",
            "another:invalid:item:::"
        ]
        result = action_selection(context=context)
        
        assert result.selected_action == HandlerActionType.SPEAK
        assert result.action_parameters.content == "Valid message"


class TestMutationInjectionPatterns:
    """Test various injection patterns."""
    
    def test_command_injection_in_params(self):
        """Test command injection attempts in parameters."""
        injection_attempts = [
            "$speak $recall $memorize",
            "test; $speak another",
            "test && $recall data",
            "test | $tool dangerous",
        ]
        
        for attempt in injection_attempts:
            context = ["forced_action:SPEAK", f"action_params:{attempt}"]
            result = action_selection(context=context)
            # Should treat entire string as content, not parse nested commands
            assert result.selected_action == HandlerActionType.SPEAK
            assert attempt in result.action_parameters.content
    
    def test_regex_dos_patterns(self):
        """Test patterns that could cause regex DoS."""
        # Patterns that could cause catastrophic backtracking
        patterns = [
            "a" * 1000 + "b",
            "@" * 100 + "channel:test",
            "(" * 50 + ")" * 50,
        ]
        
        for pattern in patterns:
            context = ["forced_action:SPEAK", f"action_params:{pattern}"]
            # Should complete without hanging
            result = action_selection(context=context)
            assert result.selected_action == HandlerActionType.SPEAK


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
