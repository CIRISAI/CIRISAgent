"""Boot-time AgentModeBroker wiring tests.

Covers the gap where ``EssentialConfig.agent_mode`` (which honors the
``AGENT_MODE`` env var) was parsed by ``load_env_vars`` but never propagated
to the module-level ``AgentModeBroker`` singleton. ``init_edge_runtime``
reads the mode through ``get_agent_mode_broker().current_mode()`` and would
have seen the broker's ``AgentMode.PROXY`` default — silently overriding
``AGENT_MODE=server``.

These tests verify both call sites:
- ``initialization_steps.init_edge_runtime`` (function-based path)
- ``CIRISRuntime._init_edge_runtime`` (method-based path on the runtime)

The boot path uses ``set_mode_sync`` because ConfigService is not yet wired
during the DATABASE phase.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.utils.agent_mode_broker import AgentModeBroker, get_agent_mode_broker
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.agent_mode import AgentMode


@pytest.fixture
def restore_broker_state():
    """Snapshot and restore the module-level broker mode around each test.

    The broker is a module-level singleton; tests that mutate it must not
    leak state into sibling tests.
    """
    broker = get_agent_mode_broker()
    saved = broker.current_mode()
    yield broker
    broker.reset_for_tests(mode=saved)


@pytest.fixture
def clean_agent_mode_env():
    """Ensure AGENT_MODE is unset around the test, restoring on exit."""
    saved = os.environ.pop("AGENT_MODE", None)
    yield
    if saved is not None:
        os.environ["AGENT_MODE"] = saved
    else:
        os.environ.pop("AGENT_MODE", None)


class TestEssentialConfigEnvParsing:
    """Sanity: EssentialConfig.load_env_vars() honors AGENT_MODE."""

    def test_no_env_defaults_to_proxy(self, clean_agent_mode_env: None) -> None:
        config = EssentialConfig()
        config.load_env_vars()
        assert config.agent_mode is AgentMode.PROXY

    def test_env_server_propagates_to_config(self, clean_agent_mode_env: None) -> None:
        os.environ["AGENT_MODE"] = "server"
        config = EssentialConfig()
        config.load_env_vars()
        assert config.agent_mode is AgentMode.SERVER

    def test_env_client_propagates_to_config(self, clean_agent_mode_env: None) -> None:
        os.environ["AGENT_MODE"] = "client"
        config = EssentialConfig()
        config.load_env_vars()
        assert config.agent_mode is AgentMode.CLIENT


class TestInitEdgeRuntimeWiringFunction:
    """initialization_steps.init_edge_runtime seeds the broker from config."""

    @pytest.mark.asyncio
    async def test_server_env_seeds_broker_as_server(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        from ciris_engine.logic.runtime.initialization_steps import init_edge_runtime

        os.environ["AGENT_MODE"] = "server"
        config = EssentialConfig()
        config.load_env_vars()

        runtime = MagicMock()
        runtime.essential_config = config

        # Pre-condition: broker default is PROXY.
        restore_broker_state.reset_for_tests(mode=AgentMode.PROXY)
        assert get_agent_mode_broker().current_mode() is AgentMode.PROXY

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime"
        ) as mock_edge_init:
            await init_edge_runtime(runtime)

        # Edge init was invoked AFTER the broker was seeded.
        mock_edge_init.assert_called_once()
        assert get_agent_mode_broker().current_mode() is AgentMode.SERVER

    @pytest.mark.asyncio
    async def test_no_env_seeds_broker_as_proxy_default(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        from ciris_engine.logic.runtime.initialization_steps import init_edge_runtime

        config = EssentialConfig()
        config.load_env_vars()
        assert config.agent_mode is AgentMode.PROXY

        runtime = MagicMock()
        runtime.essential_config = config

        # Pre-poison the broker to verify the seed actually runs (not just
        # that the value already matched).
        restore_broker_state.reset_for_tests(mode=AgentMode.SERVER)
        assert get_agent_mode_broker().current_mode() is AgentMode.SERVER

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime"
        ):
            await init_edge_runtime(runtime)

        assert get_agent_mode_broker().current_mode() is AgentMode.PROXY

    @pytest.mark.asyncio
    async def test_client_env_seeds_broker_as_client(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        from ciris_engine.logic.runtime.initialization_steps import init_edge_runtime

        os.environ["AGENT_MODE"] = "client"
        config = EssentialConfig()
        config.load_env_vars()

        runtime = MagicMock()
        runtime.essential_config = config
        restore_broker_state.reset_for_tests(mode=AgentMode.PROXY)

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime"
        ):
            await init_edge_runtime(runtime)

        assert get_agent_mode_broker().current_mode() is AgentMode.CLIENT

    @pytest.mark.asyncio
    async def test_broker_seeded_before_edge_init_called(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        """The broker MUST be seeded before initialize_edge_runtime is invoked.

        Edge reads current_mode() at the moment of its init; if the seed
        happens after, Edge gets the stale value.
        """
        from ciris_engine.logic.runtime.initialization_steps import init_edge_runtime

        os.environ["AGENT_MODE"] = "server"
        config = EssentialConfig()
        config.load_env_vars()

        runtime = MagicMock()
        runtime.essential_config = config
        restore_broker_state.reset_for_tests(mode=AgentMode.PROXY)

        observed_mode: dict[str, AgentMode] = {}

        def capture_mode_at_edge_init(*_args, **_kwargs) -> None:
            observed_mode["mode"] = get_agent_mode_broker().current_mode()

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime",
            side_effect=capture_mode_at_edge_init,
        ):
            await init_edge_runtime(runtime)

        assert observed_mode["mode"] is AgentMode.SERVER


class TestCIRISRuntimeInitEdgeMethod:
    """CIRISRuntime._init_edge_runtime method seeds the broker from config."""

    @pytest.mark.asyncio
    async def test_method_seeds_broker_from_essential_config(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        os.environ["AGENT_MODE"] = "server"
        config = EssentialConfig()
        config.load_env_vars()

        # Build a minimal-stub runtime without invoking __init__ — the
        # method only needs `essential_config` and `_ensure_config` to work.
        runtime = CIRISRuntime.__new__(CIRISRuntime)
        runtime.essential_config = config

        restore_broker_state.reset_for_tests(mode=AgentMode.PROXY)

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime"
        ):
            await runtime._init_edge_runtime()

        assert get_agent_mode_broker().current_mode() is AgentMode.SERVER

    @pytest.mark.asyncio
    async def test_method_no_env_defaults_to_proxy(
        self,
        clean_agent_mode_env: None,
        restore_broker_state: AgentModeBroker,
    ) -> None:
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        config = EssentialConfig()
        config.load_env_vars()

        runtime = CIRISRuntime.__new__(CIRISRuntime)
        runtime.essential_config = config

        # Poison broker to prove the seed runs.
        restore_broker_state.reset_for_tests(mode=AgentMode.SERVER)

        with patch(
            "ciris_engine.logic.runtime.edge_runtime.initialize_edge_runtime"
        ):
            await runtime._init_edge_runtime()

        assert get_agent_mode_broker().current_mode() is AgentMode.PROXY
