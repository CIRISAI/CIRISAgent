"""
Tests for IdentityManager helper methods to increase coverage.

Covers the refactored helper methods:
- _extract_domain_knowledge
- _extract_overrides
- _resolve_permitted_actions
- _get_default_permitted_actions
- _build_overrides_dict
- _extract_dsdma_config
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.schemas.config.agent import AgentTemplate, DSDMAConfiguration
from ciris_engine.schemas.runtime.enums import HandlerActionType


class TestExtractDomainKnowledge:
    """Tests for _extract_domain_knowledge helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_returns_empty_dict_without_dsdma_kwargs(self):
        """Returns empty dict when template has no dsdma_kwargs."""
        manager = self._create_manager()
        template = AgentTemplate(name="test", description="Test agent", role_description="Test role")

        result = manager._extract_domain_knowledge(template)

        assert result == {}

    def test_returns_empty_dict_without_domain_knowledge(self):
        """Returns empty dict when dsdma_kwargs has no domain_specific_knowledge."""
        manager = self._create_manager()
        dsdma_config = DSDMAConfiguration(prompt_template="test template")
        template = AgentTemplate(
            name="test", description="Test agent", role_description="Test role", dsdma_kwargs=dsdma_config
        )

        result = manager._extract_domain_knowledge(template)

        assert result == {}

    def test_extracts_string_domain_knowledge(self):
        """Extracts string values from domain_specific_knowledge."""
        manager = self._create_manager()
        dsdma_config = DSDMAConfiguration(domain_specific_knowledge={"key1": "value1", "key2": "value2"})
        template = AgentTemplate(
            name="test", description="Test agent", role_description="Test role", dsdma_kwargs=dsdma_config
        )

        result = manager._extract_domain_knowledge(template)

        assert result == {"key1": "value1", "key2": "value2"}

    def test_handles_dict_subvalues_in_domain_knowledge(self):
        """Handles dict values within domain_specific_knowledge sub-dicts."""
        manager = self._create_manager()
        # DSDMAConfiguration accepts Dict[str, str] | Dict[str, List[str]] | Dict[str, Dict[str, str]]
        dsdma_config = DSDMAConfiguration(
            domain_specific_knowledge={"nested": {"inner_key": "inner_value"}, "simple": "text"}
        )
        template = AgentTemplate(
            name="test", description="Test agent", role_description="Test role", dsdma_kwargs=dsdma_config
        )

        result = manager._extract_domain_knowledge(template)

        assert result["simple"] == "text"
        # Nested dict values get JSON serialized
        assert '"inner_key"' in result["nested"]
        assert '"inner_value"' in result["nested"]


class TestExtractOverrides:
    """Tests for _extract_overrides helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_returns_empty_dict_for_none(self):
        """Returns empty dict when overrides_obj is None."""
        manager = self._create_manager()

        result = manager._extract_overrides(None)

        assert result == {}

    def test_filters_none_values(self):
        """Filters out None values from overrides."""
        manager = self._create_manager()

        class MockOverrides:
            def __init__(self):
                self.system_prompt = "custom prompt"
                self.user_prompt = None
                self.temperature = 0.7

        result = manager._extract_overrides(MockOverrides())

        assert result == {"system_prompt": "custom prompt", "temperature": 0.7}
        assert "user_prompt" not in result

    def test_keeps_all_non_none_values(self):
        """Keeps all non-None values including empty strings and zeros."""
        manager = self._create_manager()

        class MockOverrides:
            def __init__(self):
                self.empty_string = ""
                self.zero = 0
                self.false_value = False
                self.actual_none = None

        result = manager._extract_overrides(MockOverrides())

        assert result == {"empty_string": "", "zero": 0, "false_value": False}
        assert "actual_none" not in result


class TestResolvePermittedActions:
    """Tests for _resolve_permitted_actions helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_uses_template_actions_when_defined(self):
        """Uses template-defined permitted_actions when present."""
        manager = self._create_manager()
        template = AgentTemplate(
            name="test",
            description="Test agent",
            role_description="Test role",
            permitted_actions=[HandlerActionType.SPEAK, HandlerActionType.OBSERVE],
        )

        result = manager._resolve_permitted_actions(template)

        assert len(result) == 2
        assert HandlerActionType.SPEAK in result
        assert HandlerActionType.OBSERVE in result

    def test_converts_string_actions_to_enum(self):
        """Converts string action names to HandlerActionType enum."""
        manager = self._create_manager()
        template = AgentTemplate(
            name="test", description="Test agent", role_description="Test role", permitted_actions=["SPEAK", "OBSERVE"]
        )

        result = manager._resolve_permitted_actions(template)

        assert len(result) == 2
        assert all(isinstance(a, HandlerActionType) for a in result)
        assert HandlerActionType.SPEAK in result
        assert HandlerActionType.OBSERVE in result

    def test_uses_defaults_when_template_has_none_via_mock(self):
        """Uses default actions when permitted_actions is None (via mock for legacy data)."""
        manager = self._create_manager()
        # Use Mock to simulate a template with None (can happen with legacy/external data)
        template = Mock()
        template.name = "test"
        template.permitted_actions = None

        result = manager._resolve_permitted_actions(template)

        # Should use default permitted actions
        default_actions = manager._get_default_permitted_actions()
        assert result == default_actions

    def test_empty_list_is_valid(self):
        """Empty list means NO actions permitted (not use defaults)."""
        manager = self._create_manager()
        template = AgentTemplate(
            name="test", description="Test agent", role_description="Test role", permitted_actions=[]
        )

        result = manager._resolve_permitted_actions(template)

        # Empty list should be respected (agent can do nothing)
        assert result == []


class TestGetDefaultPermittedActions:
    """Tests for _get_default_permitted_actions helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_returns_core_action_set(self):
        """Returns the expected set of default permitted actions."""
        manager = self._create_manager()

        result = manager._get_default_permitted_actions()

        # Verify all expected actions are present
        expected = {
            HandlerActionType.OBSERVE,
            HandlerActionType.SPEAK,
            HandlerActionType.TOOL,
            HandlerActionType.MEMORIZE,
            HandlerActionType.RECALL,
            HandlerActionType.FORGET,
            HandlerActionType.DEFER,
            HandlerActionType.REJECT,
            HandlerActionType.PONDER,
            HandlerActionType.TASK_COMPLETE,
        }
        assert set(result) == expected

    def test_returns_list_not_set(self):
        """Returns a list for consistency with template parsing."""
        manager = self._create_manager()

        result = manager._get_default_permitted_actions()

        assert isinstance(result, list)


class TestBuildOverridesDict:
    """Tests for _build_overrides_dict helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_returns_empty_for_none(self):
        """Returns empty dict when overrides is None."""
        manager = self._create_manager()

        result = manager._build_overrides_dict(None)

        assert result == {}

    def test_filters_none_values(self):
        """Filters out None values from the overrides object."""
        manager = self._create_manager()

        class MockOverrides:
            def __init__(self):
                self.value1 = "set"
                self.value2 = None

        result = manager._build_overrides_dict(MockOverrides())

        assert result == {"value1": "set"}


class TestExtractDsdmaConfig:
    """Tests for _extract_dsdma_config helper method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    def test_returns_empty_without_dsdma_kwargs(self):
        """Returns empty dict and None when no dsdma_kwargs."""
        manager = self._create_manager()
        template = AgentTemplate(name="test", description="Test", role_description="Test")

        domain_knowledge, prompt_template = manager._extract_dsdma_config(template)

        assert domain_knowledge == {}
        assert prompt_template is None

    def test_extracts_domain_knowledge_from_config(self):
        """Extracts domain_specific_knowledge from dsdma_kwargs."""
        manager = self._create_manager()
        dsdma_config = DSDMAConfiguration(domain_specific_knowledge={"key": "value"})
        template = AgentTemplate(name="test", description="Test", role_description="Test", dsdma_kwargs=dsdma_config)

        domain_knowledge, prompt_template = manager._extract_dsdma_config(template)

        assert domain_knowledge == {"key": "value"}
        assert prompt_template is None

    def test_extracts_prompt_template(self):
        """Extracts prompt_template from dsdma_kwargs."""
        manager = self._create_manager()
        dsdma_config = DSDMAConfiguration(prompt_template="Custom DSDMA template")
        template = AgentTemplate(name="test", description="Test", role_description="Test", dsdma_kwargs=dsdma_config)

        domain_knowledge, prompt_template = manager._extract_dsdma_config(template)

        assert domain_knowledge == {}
        assert prompt_template == "Custom DSDMA template"

    def test_extracts_both_when_present(self):
        """Extracts both domain_knowledge and prompt_template when present."""
        manager = self._create_manager()
        dsdma_config = DSDMAConfiguration(
            domain_specific_knowledge={"domain": "testing"}, prompt_template="Combined template"
        )
        template = AgentTemplate(name="test", description="Test", role_description="Test", dsdma_kwargs=dsdma_config)

        domain_knowledge, prompt_template = manager._extract_dsdma_config(template)

        assert domain_knowledge == {"domain": "testing"}
        assert prompt_template == "Combined template"

    def test_converts_nested_dicts_to_json(self):
        """Converts nested dict values in domain_knowledge to JSON strings."""
        manager = self._create_manager()
        nested = {"inner": "value"}
        dsdma_config = DSDMAConfiguration(domain_specific_knowledge={"nested": nested})
        template = AgentTemplate(name="test", description="Test", role_description="Test", dsdma_kwargs=dsdma_config)

        domain_knowledge, _ = manager._extract_dsdma_config(template)

        assert '"inner": "value"' in domain_knowledge["nested"]


class TestVerifyIdentityIntegrity:
    """Tests for verify_identity_integrity method."""

    def _create_manager(self):
        """Create IdentityManager with mocked dependencies."""
        from ciris_engine.logic.runtime.identity_manager import IdentityManager

        mock_config = Mock()
        mock_time_service = Mock()
        return IdentityManager(mock_config, mock_time_service)

    @pytest.mark.asyncio
    async def test_returns_false_without_identity(self):
        """Returns False when no agent identity is loaded."""
        manager = self._create_manager()
        manager.agent_identity = None

        result = await manager.verify_identity_integrity()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_missing_agent_id(self):
        """Returns False when identity is missing agent_id."""
        manager = self._create_manager()
        manager.agent_identity = Mock()
        manager.agent_identity.agent_id = None
        manager.agent_identity.identity_hash = "hash"
        manager.agent_identity.core_profile = Mock()

        result = await manager.verify_identity_integrity()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_with_valid_identity(self):
        """Returns True when identity has all required fields."""
        manager = self._create_manager()
        manager.agent_identity = Mock()
        manager.agent_identity.agent_id = "test-agent"
        manager.agent_identity.identity_hash = "abc123"
        manager.agent_identity.core_profile = Mock()

        result = await manager.verify_identity_integrity()

        assert result is True
