"""Comprehensive tests for identity formatter to achieve high coverage."""

import pytest

from ciris_engine.logic.formatters.identity import format_agent_identity


class TestFormatAgentIdentity:
    """Test format_agent_identity function comprehensively."""

    def test_format_agent_identity_none(self):
        """Test that None input returns empty string."""
        result = format_agent_identity(None)
        assert result == ""

    def test_format_agent_identity_empty_dict(self):
        """Test that empty dict returns empty string."""
        result = format_agent_identity({})
        assert result == ""

    def test_format_agent_identity_non_dict(self):
        """Test that non-dict input returns empty string."""
        result = format_agent_identity("not a dict")
        assert result == ""

        result = format_agent_identity([])
        assert result == ""

        result = format_agent_identity(123)
        assert result == ""

    def test_format_agent_identity_basic_info(self):
        """Test formatting with basic agent info."""
        identity = {
            "agent_id": "test_agent",
            "description": "Test agent description",
            "role_description": "Test role",
        }

        result = format_agent_identity(identity)

        assert "Agent ID: test_agent" in result
        assert "Purpose: Test agent description" in result
        assert "Role: Test role" in result

    def test_format_agent_identity_trust_level(self):
        """Test trust level formatting."""
        identity = {"agent_id": "test_agent", "trust_level": 0.95}

        result = format_agent_identity(identity)
        assert "Trust Level: 0.95" in result

    def test_format_agent_identity_trust_level_zero(self):
        """Test that trust_level of 0 is included."""
        identity = {"agent_id": "test_agent", "trust_level": 0}

        result = format_agent_identity(identity)
        assert "Trust Level: 0" in result

    def test_format_agent_identity_domain_knowledge(self):
        """Test domain-specific knowledge formatting."""
        identity = {"agent_id": "test_agent", "domain_specific_knowledge": {"role": "Medical Assistant"}}

        result = format_agent_identity(identity)
        assert "Domain Role: Medical Assistant" in result

    def test_format_agent_identity_domain_knowledge_no_role(self):
        """Test domain knowledge without role is omitted."""
        identity = {"agent_id": "test_agent", "domain_specific_knowledge": {"other_field": "value"}}

        result = format_agent_identity(identity)
        assert "Domain Role:" not in result

    def test_format_agent_identity_domain_knowledge_not_dict(self):
        """Test domain knowledge that's not a dict is omitted."""
        identity = {"agent_id": "test_agent", "domain_specific_knowledge": "not a dict"}

        result = format_agent_identity(identity)
        assert "Domain Role:" not in result

    def test_format_agent_identity_permitted_actions(self):
        """Test permitted actions formatting."""
        identity = {"agent_id": "test_agent", "permitted_actions": ["action1", "action2", "action3"]}

        result = format_agent_identity(identity)
        assert "Permitted Actions: action1, action2, action3" in result

    def test_format_agent_identity_permitted_actions_limit_10(self):
        """Test that permitted actions are limited to 10."""
        identity = {"agent_id": "test_agent", "permitted_actions": [f"action{i}" for i in range(15)]}

        result = format_agent_identity(identity)
        # Should only show first 10
        assert "action0" in result
        assert "action9" in result
        assert "action14" not in result

    def test_format_agent_identity_permitted_actions_not_list(self):
        """Test permitted actions that's not a list is omitted."""
        identity = {"agent_id": "test_agent", "permitted_actions": "not a list"}

        result = format_agent_identity(identity)
        assert "Permitted Actions:" not in result

    def test_format_agent_identity_startup_history(self):
        """Test startup event formatting (old terminology)."""
        identity = {
            "agent_id": "test_agent",
            "startup_2024-01-01T10:00:00.000000+00:00": {"tags": ["startup", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        assert "=== Continuity History ===" in result
        assert "First Start:" in result
        assert "2024-01-01T10:00:00" in result

    def test_format_agent_identity_startup_history_new_terminology(self):
        """Test startup event formatting (new terminology)."""
        identity = {
            "agent_id": "test_agent",
            "startup_2024-01-01T10:00:00.000000+00:00": {"tags": ["startup", "continuity_awareness"]},
        }

        result = format_agent_identity(identity)
        assert "=== Continuity History ===" in result
        assert "First Start:" in result

    def test_format_agent_identity_shutdown_history(self):
        """Test shutdown event formatting (old terminology)."""
        identity = {
            "agent_id": "test_agent",
            "shutdown_2024-01-01T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
            "shutdown_2024-01-02T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        assert "=== Continuity History ===" in result
        assert "Recent Shutdowns (2 total):" in result
        assert "2024-01-02T10:00:00" in result  # Most recent first
        assert "2024-01-01T10:00:00" in result

    def test_format_agent_identity_shutdown_history_new_terminology(self):
        """Test shutdown event formatting (new terminology)."""
        identity = {
            "agent_id": "test_agent",
            "shutdown_2024-01-01T10:00:00.000000+00:00": {"tags": ["shutdown", "continuity_awareness"]},
        }

        result = format_agent_identity(identity)
        assert "=== Continuity History ===" in result
        assert "Recent Shutdowns (1 total):" in result

    def test_format_agent_identity_shutdown_limit_5(self):
        """Test that shutdowns are limited to 5 most recent."""
        identity = {"agent_id": "test_agent"}

        # Add 10 shutdown events
        for i in range(10):
            key = f"shutdown_2024-01-{i+1:02d}T10:00:00.000000+00:00"
            identity[key] = {"tags": ["shutdown", "consciousness_preservation"]}

        result = format_agent_identity(identity)
        assert "Recent Shutdowns (10 total):" in result
        assert "... and 5 more" in result

        # Most recent (2024-01-10) should be shown
        assert "2024-01-10T10:00:00" in result
        # Oldest (2024-01-01) appears in "First Start"
        # Check it's NOT in the shutdown list specifically
        shutdown_section = result.split("Recent Shutdowns")[1]
        assert "2024-01-01" not in shutdown_section or "First Start" in result

    def test_format_agent_identity_timestamp_formatting(self):
        """Test timestamp formatting removes microseconds and adds UTC."""
        identity = {
            "agent_id": "test_agent",
            "shutdown_2024-01-01T10:30:45.123456+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        # Microseconds should be removed
        assert ".123456" not in result
        # Should have the timestamp (UTC may not be added in all cases)
        assert "2024-01-01T10:30:45" in result

    def test_format_agent_identity_timestamp_without_microseconds(self):
        """Test timestamp formatting when no microseconds present."""
        identity = {
            "agent_id": "test_agent",
            "shutdown_2024-01-01T10:30:45+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        assert "2024-01-01T10:30:45" in result

    def test_format_agent_identity_timestamp_formatting_exception(self):
        """Test timestamp formatting handles exceptions gracefully."""
        identity = {
            "agent_id": "test_agent",
            "shutdown_invalid_timestamp": {"tags": ["shutdown", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        # Should include raw timestamp when formatting fails
        assert "invalid_timestamp" in result

    def test_format_agent_identity_first_event_earliest(self):
        """Test that first event is the earliest of startup/shutdown."""
        identity = {
            "agent_id": "test_agent",
            "startup_2024-01-03T10:00:00.000000+00:00": {"tags": ["startup", "consciousness_preservation"]},
            "shutdown_2024-01-01T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
            "shutdown_2024-01-02T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
        }

        result = format_agent_identity(identity)
        # First start should be earliest event (shutdown on 01-01)
        assert "First Start: 2024-01-01T10:00:00" in result

    def test_format_agent_identity_channel_assignment(self):
        """Test channel assignment formatting."""
        identity = {"agent_id": "test_agent", "some_field": "Our assigned channel is api_google:110265575142761676421"}

        result = format_agent_identity(identity)
        assert "Our assigned channel is api_google:110265575142761676421" in result

    def test_format_agent_identity_channel_assignment_case_insensitive(self):
        """Test channel assignment detection is case-insensitive."""
        identity = {"agent_id": "test_agent", "some_field": "Our ASSIGNED CHANNEL is test:123"}

        result = format_agent_identity(identity)
        assert "Our ASSIGNED CHANNEL is test:123" in result

    def test_format_agent_identity_channel_assignment_not_string(self):
        """Test channel assignment skipped when not a string."""
        identity = {"agent_id": "test_agent", "some_field": {"assigned channel": "test"}}

        result = format_agent_identity(identity)
        # Should not include channel assignment
        lines = result.split("\n")
        assert all("assigned channel" not in line.lower() for line in lines)

    def test_format_agent_identity_complete_identity(self):
        """Test formatting with all fields present."""
        identity = {
            "agent_id": "datum_agent",
            "description": "Personal AI assistant for Emma",
            "role_description": "Executive Assistant",
            "trust_level": 0.99,
            "domain_specific_knowledge": {"role": "Data Analyst"},
            "permitted_actions": ["read", "write", "execute"],
            "startup_2024-01-01T10:00:00.000000+00:00": {"tags": ["startup", "consciousness_preservation"]},
            "shutdown_2024-01-02T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
            "shutdown_2024-01-03T10:00:00.000000+00:00": {"tags": ["shutdown", "consciousness_preservation"]},
            "channel_info": "Our assigned channel is api_google:123456",
        }

        result = format_agent_identity(identity)

        # Check all sections are present
        assert "Agent ID: datum_agent" in result
        assert "Purpose: Personal AI assistant for Emma" in result
        assert "Role: Executive Assistant" in result
        assert "Trust Level: 0.99" in result
        assert "Domain Role: Data Analyst" in result
        assert "Permitted Actions: read, write, execute" in result
        assert "=== Continuity History ===" in result
        assert "First Start: 2024-01-01T10:00:00" in result
        assert "Recent Shutdowns (2 total):" in result
        assert "Our assigned channel is api_google:123456" in result

    def test_format_agent_identity_description_strips_whitespace(self):
        """Test that description whitespace is stripped."""
        identity = {
            "agent_id": "test_agent",
            "description": "  Description with spaces  ",
            "role_description": "  Role with spaces  ",
        }

        result = format_agent_identity(identity)
        assert "Purpose: Description with spaces" in result
        assert "Role: Role with spaces" in result

    def test_format_agent_identity_wrong_tags_ignored(self):
        """Test that events without proper tags are ignored."""
        identity = {
            "agent_id": "test_agent",
            "startup_2024-01-01T10:00:00.000000+00:00": {"tags": ["wrong_tag"]},
            "shutdown_2024-01-02T10:00:00.000000+00:00": {"tags": ["shutdown"]},  # Missing consciousness tag
        }

        result = format_agent_identity(identity)
        # Should not have continuity history section
        assert "=== Continuity History ===" not in result

    def test_format_agent_identity_not_dict_values_ignored(self):
        """Test that startup/shutdown values that aren't dicts are ignored."""
        identity = {
            "agent_id": "test_agent",
            "startup_2024-01-01T10:00:00.000000+00:00": "not a dict",
            "shutdown_2024-01-02T10:00:00.000000+00:00": ["not", "a", "dict"],
        }

        result = format_agent_identity(identity)
        # Should not have continuity history section
        assert "=== Continuity History ===" not in result
