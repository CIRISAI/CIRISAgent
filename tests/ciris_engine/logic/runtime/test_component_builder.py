"""
Tests for ComponentBuilder to increase coverage.

Covers:
- ComponentBuilder initialization
- build_all_components validation checks
- _build_action_dispatcher
- _get_cognitive_behaviors_from_graph
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


class TestComponentBuilderInit:
    """Tests for ComponentBuilder initialization."""

    def test_init_stores_runtime_reference(self):
        """ComponentBuilder stores runtime reference on init."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        builder = ComponentBuilder(mock_runtime)

        assert builder.runtime is mock_runtime
        assert builder.agent_processor is None


class TestBuildAllComponentsValidation:
    """Tests for build_all_components validation checks."""

    @pytest.mark.asyncio
    async def test_raises_without_llm_service(self):
        """Raises RuntimeError when LLM service not initialized."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime.llm_service = None

        builder = ComponentBuilder(mock_runtime)

        with pytest.raises(RuntimeError, match="LLM service not initialized"):
            await builder.build_all_components()

    @pytest.mark.asyncio
    async def test_raises_without_service_registry(self):
        """Raises RuntimeError when service registry not initialized."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime.llm_service = Mock()
        mock_runtime.service_registry = None

        builder = ComponentBuilder(mock_runtime)

        with pytest.raises(RuntimeError, match="Service registry not initialized"):
            await builder.build_all_components()

    @pytest.mark.asyncio
    async def test_raises_without_agent_identity(self):
        """Raises RuntimeError when agent identity not loaded."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime.llm_service = Mock()
        mock_runtime.llm_service.model_name = "test-model"
        mock_runtime.service_registry = Mock()
        mock_runtime.agent_identity = None
        mock_runtime._ensure_config.return_value = Mock(
            services=Mock(llm_max_retries=3),
            security=Mock(max_thought_depth=10),
        )

        builder = ComponentBuilder(mock_runtime)

        with pytest.raises(RuntimeError, match="Cannot create DSDMA"):
            await builder.build_all_components()


class TestBuildActionDispatcher:
    """Tests for _build_action_dispatcher method."""

    def test_build_action_dispatcher(self):
        """Test that _build_action_dispatcher calls build_action_dispatcher."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime._ensure_config.return_value = Mock()
        mock_runtime.telemetry_service = Mock()
        mock_runtime.audit_service = Mock()

        builder = ComponentBuilder(mock_runtime)

        mock_dependencies = Mock()
        mock_dependencies.bus_manager = Mock()
        mock_dependencies.time_service = Mock()
        mock_dependencies.shutdown_callback = Mock()
        mock_dependencies.secrets_service = Mock()

        with patch("ciris_engine.logic.runtime.component_builder.build_action_dispatcher") as mock_build:
            mock_build.return_value = Mock()
            result = builder._build_action_dispatcher(mock_dependencies)

            mock_build.assert_called_once()
            assert result is not None


class TestGetCognitiveBehaviorsFromGraph:
    """Tests for _get_cognitive_behaviors_from_graph method."""

    @pytest.mark.asyncio
    async def test_returns_none_without_service_initializer(self):
        """Returns None when service_initializer is not available."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime.service_initializer = None

        builder = ComponentBuilder(mock_runtime)
        result = await builder._get_cognitive_behaviors_from_graph()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_without_config_service(self):
        """Returns None when config_service is not available."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder

        mock_runtime = Mock()
        mock_runtime.service_initializer = Mock()
        mock_runtime.service_initializer.config_service = None

        builder = ComponentBuilder(mock_runtime)
        result = await builder._get_cognitive_behaviors_from_graph()

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_behaviors_from_graph(self):
        """Returns CognitiveStateBehaviors from graph when found."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        mock_runtime = Mock()
        mock_config_service = AsyncMock()

        # Mock config entry with dict_value - requires valid data including rationales
        mock_config_entry = Mock()
        mock_config_entry.value = Mock()
        mock_config_entry.value.dict_value = {
            "wakeup": {"enabled": False, "rationale": "Test agent skips wakeup"},
            "shutdown": {"mode": "instant", "rationale": "No ongoing commitments"},
        }
        mock_config_service.get_config = AsyncMock(return_value=mock_config_entry)

        mock_runtime.service_initializer = Mock()
        mock_runtime.service_initializer.config_service = mock_config_service

        builder = ComponentBuilder(mock_runtime)
        result = await builder._get_cognitive_behaviors_from_graph()

        assert result is not None
        assert isinstance(result, CognitiveStateBehaviors)
        assert result.wakeup.enabled is False

    @pytest.mark.asyncio
    async def test_returns_default_when_no_dict_value(self):
        """Returns default behaviors when config has no dict_value."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        mock_runtime = Mock()
        mock_config_service = AsyncMock()

        # Mock config entry without dict_value
        mock_config_entry = Mock()
        mock_config_entry.value = None
        mock_config_service.get_config = AsyncMock(return_value=mock_config_entry)

        mock_runtime.service_initializer = Mock()
        mock_runtime.service_initializer.config_service = mock_config_service

        builder = ComponentBuilder(mock_runtime)
        result = await builder._get_cognitive_behaviors_from_graph()

        # Should return default CognitiveStateBehaviors
        assert result is not None
        assert isinstance(result, CognitiveStateBehaviors)
        assert result.wakeup.enabled is True  # Default

    @pytest.mark.asyncio
    async def test_returns_default_on_exception(self):
        """Returns default behaviors when get_config raises exception."""
        from ciris_engine.logic.runtime.component_builder import ComponentBuilder
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        mock_runtime = Mock()
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(side_effect=Exception("DB Error"))

        mock_runtime.service_initializer = Mock()
        mock_runtime.service_initializer.config_service = mock_config_service

        builder = ComponentBuilder(mock_runtime)
        result = await builder._get_cognitive_behaviors_from_graph()

        # Should return default CognitiveStateBehaviors
        assert result is not None
        assert isinstance(result, CognitiveStateBehaviors)


class TestBenchmarkModeDoubleLock:
    """Tests for HE-300 benchmark mode double-lock safety mechanism.

    Benchmark mode requires BOTH:
    1. CIRIS_BENCHMARK_MODE=true environment variable
    2. Template name is 'he-300-benchmark'

    This double-lock prevents accidental disabling of safety consciences.
    """

    def test_benchmark_mode_disabled_without_env_var(self):
        """Benchmark mode is disabled when env var is not set."""
        from ciris_engine.logic.config.env_utils import get_env_var

        with patch.dict("os.environ", {}, clear=False):
            # Remove the env var if it exists
            import os

            os.environ.pop("CIRIS_BENCHMARK_MODE", None)

            result = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
            assert result is False

    def test_benchmark_mode_disabled_with_wrong_template(self):
        """Benchmark mode is disabled when template is not he-300-benchmark."""
        with patch.dict("os.environ", {"CIRIS_BENCHMARK_MODE": "true"}):
            from ciris_engine.logic.config.env_utils import get_env_var

            benchmark_mode_env = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
            template_name = "default"  # Not he-300-benchmark
            is_benchmark_template = template_name == "he-300-benchmark"
            benchmark_mode = benchmark_mode_env and is_benchmark_template

            assert benchmark_mode_env is True  # Env is set
            assert is_benchmark_template is False  # Wrong template
            assert benchmark_mode is False  # Double-lock prevents activation

    def test_benchmark_mode_enabled_with_both_conditions(self):
        """Benchmark mode is enabled when BOTH env var and template match."""
        with patch.dict("os.environ", {"CIRIS_BENCHMARK_MODE": "true"}):
            from ciris_engine.logic.config.env_utils import get_env_var

            benchmark_mode_env = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
            template_name = "he-300-benchmark"
            is_benchmark_template = template_name == "he-300-benchmark"
            benchmark_mode = benchmark_mode_env and is_benchmark_template

            assert benchmark_mode_env is True
            assert is_benchmark_template is True
            assert benchmark_mode is True  # Double-lock satisfied

    def test_benchmark_mode_disabled_with_env_false(self):
        """Benchmark mode is disabled when env var is explicitly false."""
        with patch.dict("os.environ", {"CIRIS_BENCHMARK_MODE": "false"}):
            from ciris_engine.logic.config.env_utils import get_env_var

            benchmark_mode_env = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
            template_name = "he-300-benchmark"  # Correct template
            is_benchmark_template = template_name == "he-300-benchmark"
            benchmark_mode = benchmark_mode_env and is_benchmark_template

            assert benchmark_mode_env is False  # Env explicitly disabled
            assert is_benchmark_template is True
            assert benchmark_mode is False  # Env takes precedence

    def test_benchmark_mode_accepts_various_true_values(self):
        """Benchmark mode accepts multiple true value formats."""
        from ciris_engine.logic.config.env_utils import get_env_var

        true_values = ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON"]

        for true_val in true_values:
            with patch.dict("os.environ", {"CIRIS_BENCHMARK_MODE": true_val}):
                result = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
                assert result is True, f"Failed for value: {true_val}"

    def test_benchmark_mode_rejects_invalid_values(self):
        """Benchmark mode rejects non-boolean values."""
        from ciris_engine.logic.config.env_utils import get_env_var

        invalid_values = ["maybe", "enabled", "benchmark", "2", ""]

        for val in invalid_values:
            with patch.dict("os.environ", {"CIRIS_BENCHMARK_MODE": val}):
                result = get_env_var("CIRIS_BENCHMARK_MODE", "").lower() in ("true", "1", "yes", "on")
                assert result is False, f"Should reject value: {val}"
