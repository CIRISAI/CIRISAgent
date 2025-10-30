"""Unit tests for hot/cold path telemetry configuration.

Tests verify that telemetry path classification and requirements
work correctly for hot, cold, and critical code paths.
"""

import pytest

from ciris_engine.logic.telemetry.hot_cold_config import (
    HOT_COLD_PATH_CONFIG,
    MODULE_CONFIGS,
    PathConfig,
    get_path_config,
    get_telemetry_requirements,
    is_critical_function,
    is_hot_path,
)


class TestPathConfig:
    """Test PathConfig dataclass."""

    def test_path_config_creation(self):
        """Test creating a PathConfig."""
        config = PathConfig(
            path_type="hot",
            telemetry_required=True,
            retention_policy="raw",
            alert_threshold_ms=100.0,
            sampling_rate=1.0,
        )

        assert config.path_type == "hot"
        assert config.telemetry_required is True
        assert config.retention_policy == "raw"
        assert config.alert_threshold_ms == 100.0
        assert config.sampling_rate == 1.0

    def test_path_config_defaults(self):
        """Test PathConfig with default sampling_rate."""
        config = PathConfig(
            path_type="critical",
            telemetry_required=True,
            retention_policy="raw",
            alert_threshold_ms=5.0,
        )

        assert config.sampling_rate == 1.0  # Default value


class TestHotColdPathConfig:
    """Test HOT_COLD_PATH_CONFIG dictionary."""

    def test_critical_paths_configured(self):
        """Test that critical paths are properly configured."""
        critical_paths = ["audit_log", "security_check", "auth_verification", "error_handler", "circuit_breaker"]

        for path in critical_paths:
            assert path in HOT_COLD_PATH_CONFIG
            config = HOT_COLD_PATH_CONFIG[path]
            assert config.path_type == "critical"
            assert config.telemetry_required is True
            assert config.retention_policy == "raw"

    def test_hot_paths_configured(self):
        """Test that hot paths are properly configured."""
        hot_paths = [
            "thought_processing",
            "action_selection",
            "handler_invocation",
            "dma_execution",
            "conscience_check",
        ]

        for path in hot_paths:
            assert path in HOT_COLD_PATH_CONFIG
            config = HOT_COLD_PATH_CONFIG[path]
            assert config.path_type == "hot"
            assert config.telemetry_required is True

    def test_cold_paths_configured(self):
        """Test that cold paths are properly configured."""
        cold_paths = ["memory_operation", "persistence_fetch", "context_fetch", "telemetry_aggregation"]

        for path in cold_paths:
            assert path in HOT_COLD_PATH_CONFIG
            config = HOT_COLD_PATH_CONFIG[path]
            assert config.path_type == "cold"
            assert config.telemetry_required is False

    def test_critical_paths_have_low_thresholds(self):
        """Test that critical paths have aggressive alert thresholds."""
        critical_config = HOT_COLD_PATH_CONFIG["auth_verification"]
        assert critical_config.alert_threshold_ms <= 10.0

    def test_cold_paths_have_sampling(self):
        """Test that cold paths use reduced sampling rates."""
        cold_config = HOT_COLD_PATH_CONFIG["telemetry_aggregation"]
        assert cold_config.sampling_rate < 1.0


class TestGetPathConfig:
    """Test get_path_config function."""

    def test_exact_match(self):
        """Test exact metric name match."""
        config = get_path_config("audit_log")

        assert config.path_type == "critical"
        assert config.telemetry_required is True
        assert config.retention_policy == "raw"

    def test_prefix_match(self):
        """Test prefix matching for metric names."""
        config = get_path_config("thought_processing_started")

        assert config.path_type == "hot"
        assert config.telemetry_required is True

    def test_unknown_metric_default(self):
        """Test default config for unknown metric."""
        config = get_path_config("unknown_metric_name")

        assert config.path_type == "normal"
        assert config.telemetry_required is False
        assert config.retention_policy == "aggregated"
        assert config.alert_threshold_ms == 1000.0
        assert config.sampling_rate == 0.1

    def test_multiple_prefix_matches(self):
        """Test that first matching prefix is used."""
        # "dma_execution_started" should match "dma_execution"
        config = get_path_config("dma_execution_started")

        assert config.path_type == "hot"
        assert config.alert_threshold_ms == 150.0


class TestModuleConfigs:
    """Test MODULE_CONFIGS dictionary."""

    def test_thought_processor_config(self):
        """Test thought processor module configuration."""
        config = MODULE_CONFIGS["ciris_engine.processor.thought_processor"]

        assert config.module_name == "thought_processor"
        assert "Thought" in config.hot_types
        assert "ActionSelectionDMAResult" in config.hot_types
        assert "ConscienceResult" in config.cold_types
        assert "process_thought" in config.critical_functions

    def test_action_handlers_config(self):
        """Test action handlers module configuration."""
        config = MODULE_CONFIGS["ciris_engine.action_handlers"]

        assert config.module_name == "action_handlers"
        assert "ActionSelectionDMAResult" in config.hot_types
        assert "AuditLogEntry" in config.cold_types
        assert "dispatch" in config.critical_functions
        assert "handle" in config.critical_functions

    def test_dma_config(self):
        """Test DMA module configuration."""
        config = MODULE_CONFIGS["ciris_engine.dma"]

        assert config.module_name == "dma"
        assert "EthicalDMAResult" in config.hot_types
        assert "CSDMAResult" in config.hot_types
        assert "DSDMAResult" in config.hot_types
        assert "DMAMetrics" in config.cold_types
        assert "evaluate" in config.critical_functions


class TestIsHotPath:
    """Test is_hot_path function."""

    def test_hot_type_in_module(self):
        """Test that hot types are correctly identified."""
        assert is_hot_path("ciris_engine.processor.thought_processor", "Thought") is True
        assert is_hot_path("ciris_engine.dma", "EthicalDMAResult") is True

    def test_cold_type_in_module(self):
        """Test that cold types are not identified as hot."""
        assert is_hot_path("ciris_engine.processor.thought_processor", "ConscienceResult") is False
        assert is_hot_path("ciris_engine.dma", "DMAMetrics") is False

    def test_unknown_type(self):
        """Test that unknown types return False."""
        assert is_hot_path("ciris_engine.processor.thought_processor", "UnknownType") is False

    def test_unknown_module(self):
        """Test that unknown modules return False."""
        assert is_hot_path("unknown.module", "Thought") is False

    def test_partial_module_match(self):
        """Test that partial module paths work."""
        # "thought_processor" should match in "ciris_engine.processor.thought_processor.submodule"
        assert is_hot_path("ciris_engine.processor.thought_processor.submodule", "Thought") is True


class TestIsCriticalFunction:
    """Test is_critical_function function."""

    def test_critical_function_in_module(self):
        """Test that critical functions are correctly identified."""
        assert is_critical_function("ciris_engine.processor.thought_processor", "process_thought") is True
        assert is_critical_function("ciris_engine.action_handlers", "dispatch") is True
        assert is_critical_function("ciris_engine.dma", "evaluate") is True

    def test_non_critical_function(self):
        """Test that non-critical functions return False."""
        assert is_critical_function("ciris_engine.processor.thought_processor", "random_helper") is False

    def test_unknown_module(self):
        """Test that unknown modules return False."""
        assert is_critical_function("unknown.module", "process_thought") is False

    def test_partial_module_match(self):
        """Test that partial module paths work."""
        assert is_critical_function("ciris_engine.action_handlers.submodule", "dispatch") is True


class TestGetTelemetryRequirements:
    """Test get_telemetry_requirements function."""

    def test_critical_operation_requirements(self):
        """Test telemetry requirements for critical operations."""
        reqs = get_telemetry_requirements("ciris_engine.audit", "audit_log")

        assert reqs["enabled"] is True
        assert reqs["path_type"] == "critical"
        assert reqs["retention_policy"] == "raw"
        assert reqs["sampling_rate"] == 1.0
        assert reqs["alert_threshold_ms"] == 10.0

    def test_hot_operation_requirements(self):
        """Test telemetry requirements for hot operations."""
        reqs = get_telemetry_requirements("ciris_engine.processor", "thought_processing")

        assert reqs["enabled"] is True
        assert reqs["path_type"] == "hot"
        assert reqs["retention_policy"] == "raw"
        assert reqs["sampling_rate"] == 1.0
        assert reqs["alert_threshold_ms"] == 100.0

    def test_cold_operation_requirements(self):
        """Test telemetry requirements for cold operations."""
        reqs = get_telemetry_requirements("ciris_engine.memory", "memory_operation")

        assert reqs["enabled"] is False
        assert reqs["path_type"] == "cold"
        assert reqs["retention_policy"] == "aggregated"
        assert reqs["sampling_rate"] == 0.1
        assert reqs["alert_threshold_ms"] == 1000.0

    def test_unknown_operation_requirements(self):
        """Test telemetry requirements for unknown operations."""
        reqs = get_telemetry_requirements("unknown.module", "unknown_operation")

        assert reqs["enabled"] is False
        assert reqs["path_type"] == "normal"
        assert reqs["retention_policy"] == "aggregated"
        assert reqs["sampling_rate"] == 0.1
        assert reqs["alert_threshold_ms"] == 1000.0

    def test_all_required_keys_present(self):
        """Test that all required keys are in the returned dict."""
        reqs = get_telemetry_requirements("test", "test_operation")

        required_keys = ["enabled", "path_type", "retention_policy", "sampling_rate", "alert_threshold_ms"]
        for key in required_keys:
            assert key in reqs
