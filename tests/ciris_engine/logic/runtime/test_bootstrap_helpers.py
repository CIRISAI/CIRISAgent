"""Tests for bootstrap_helpers.py module."""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestBootstrapHelpers:
    """Tests for bootstrap configuration helpers."""

    def test_check_mock_llm_adds_module(self) -> None:
        """Test that mock_llm module is added when env var is set."""
        from ciris_engine.logic.runtime.bootstrap_helpers import check_mock_llm

        runtime = MagicMock()
        runtime.modules_to_load = []

        with patch.dict(os.environ, {"CIRIS_MOCK_LLM": "true"}):
            check_mock_llm(runtime)

        assert "mock_llm" in runtime.modules_to_load

    def test_check_mock_llm_does_not_duplicate(self) -> None:
        """Test that mock_llm is not duplicated if already in list."""
        from ciris_engine.logic.runtime.bootstrap_helpers import check_mock_llm

        runtime = MagicMock()
        runtime.modules_to_load = ["mock_llm"]

        with patch.dict(os.environ, {"CIRIS_MOCK_LLM": "true"}):
            check_mock_llm(runtime)

        assert runtime.modules_to_load.count("mock_llm") == 1

    def test_check_mock_llm_ignores_when_not_set(self) -> None:
        """Test that nothing is added when env var is not set."""
        from ciris_engine.logic.runtime.bootstrap_helpers import check_mock_llm

        runtime = MagicMock()
        runtime.modules_to_load = []

        with patch.dict(os.environ, {}, clear=True):
            # Make sure CIRIS_MOCK_LLM is not set
            os.environ.pop("CIRIS_MOCK_LLM", None)
            check_mock_llm(runtime)

        assert "mock_llm" not in runtime.modules_to_load

    def test_parse_bootstrap_config_with_bootstrap(self) -> None:
        """Test parsing with a RuntimeBootstrapConfig."""
        from ciris_engine.logic.runtime.bootstrap_helpers import parse_bootstrap_config
        from ciris_engine.schemas.config.essential import EssentialConfig
        from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

        runtime = MagicMock()
        bootstrap = RuntimeBootstrapConfig(
            adapters=[],
            adapter_overrides={},
            modules=["test_module"],
            startup_channel_id="test_channel",
            debug=True,
            preload_tasks=["task1"],
        )

        parse_bootstrap_config(
            runtime=runtime,
            bootstrap=bootstrap,
            essential_config=None,
            startup_channel_id=None,
            adapter_types=[],
            adapter_configs=None,
            kwargs={},
        )

        assert runtime.bootstrap is bootstrap
        assert runtime.startup_channel_id == "test_channel"
        assert runtime.modules_to_load == ["test_module"]
        assert runtime.debug is True

    def test_create_bootstrap_from_legacy(self) -> None:
        """Test creating bootstrap config from legacy parameters."""
        from ciris_engine.logic.runtime.bootstrap_helpers import create_bootstrap_from_legacy
        from ciris_engine.schemas.config.essential import EssentialConfig

        runtime = MagicMock()
        essential_config = EssentialConfig()

        create_bootstrap_from_legacy(
            runtime=runtime,
            essential_config=essential_config,
            startup_channel_id="legacy_channel",
            adapter_types=["api", "discord"],
            adapter_configs=None,
            kwargs={"modules": ["mod1", "mod2"], "debug": True},
        )

        assert runtime.essential_config is essential_config
        assert runtime.startup_channel_id == "legacy_channel"
        assert runtime.modules_to_load == ["mod1", "mod2"]
        assert runtime.debug is True
        # Bootstrap should be created
        assert runtime.bootstrap is not None
        assert len(runtime.bootstrap.adapters) == 2
