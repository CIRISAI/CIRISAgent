"""Tests for ToolBus tool alias support."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.buses.tool_bus import ToolBus


class TestToolBusAliases:
    """Tests for the tool alias mechanism in ToolBus."""

    def _create_tool_bus(self) -> ToolBus:
        """Create a ToolBus with mocked dependencies."""
        registry = MagicMock()
        registry._services = {}
        time_service = MagicMock()
        time_service.now.return_value = None
        return ToolBus(service_registry=registry, time_service=time_service)

    def test_register_alias(self):
        bus = self._create_tool_bus()
        bus.register_tool_alias("todoist", "skill:todoist-cli")
        assert bus._tool_aliases["todoist"] == "skill:todoist-cli"

    def test_resolve_alias(self):
        bus = self._create_tool_bus()
        bus.register_tool_alias("todoist", "skill:todoist-cli")
        assert bus.resolve_tool_name("todoist") == "skill:todoist-cli"

    def test_resolve_unknown_name_returns_self(self):
        bus = self._create_tool_bus()
        assert bus.resolve_tool_name("unknown-tool") == "unknown-tool"

    def test_resolve_canonical_name_returns_self(self):
        bus = self._create_tool_bus()
        bus.register_tool_alias("todoist", "skill:todoist-cli")
        # Canonical name should not be aliased
        assert bus.resolve_tool_name("skill:todoist-cli") == "skill:todoist-cli"

    def test_multiple_aliases_same_target(self):
        bus = self._create_tool_bus()
        bus.register_tool_alias("todoist", "skill:todoist-cli")
        bus.register_tool_alias("todo", "skill:todoist-cli")
        assert bus.resolve_tool_name("todoist") == "skill:todoist-cli"
        assert bus.resolve_tool_name("todo") == "skill:todoist-cli"

    def test_alias_override(self):
        bus = self._create_tool_bus()
        bus.register_tool_alias("todoist", "skill:todoist-cli")
        bus.register_tool_alias("todoist", "skill:todoist-v2")
        assert bus.resolve_tool_name("todoist") == "skill:todoist-v2"
