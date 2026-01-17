"""
Bootstrap configuration helpers for CIRISRuntime.

Handles parsing bootstrap configuration, creating runtime from legacy parameters,
and loading adapters from bootstrap config.
"""

import logging
import os
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

logger = logging.getLogger(__name__)


def parse_bootstrap_config(
    runtime: Any,
    bootstrap: Optional["RuntimeBootstrapConfig"],
    essential_config: Optional[EssentialConfig],
    startup_channel_id: Optional[str],
    adapter_types: List[str],
    adapter_configs: Optional[Dict[str, AdapterConfig]],
    kwargs: JSONDict,
) -> None:
    """Parse bootstrap configuration or create from legacy parameters.

    Args:
        runtime: The CIRISRuntime instance to configure
        bootstrap: Optional RuntimeBootstrapConfig
        essential_config: Optional EssentialConfig
        startup_channel_id: Optional startup channel ID
        adapter_types: List of adapter type names
        adapter_configs: Optional dict of adapter configurations
        kwargs: Additional keyword arguments
    """
    if bootstrap is not None:
        runtime.bootstrap = bootstrap
        runtime.essential_config = essential_config or EssentialConfig()
        runtime.essential_config.load_env_vars()
        runtime.startup_channel_id = bootstrap.startup_channel_id or ""
        runtime.adapter_configs = bootstrap.adapter_overrides
        runtime.modules_to_load = bootstrap.modules
        runtime.debug = bootstrap.debug
        runtime._preload_tasks = bootstrap.preload_tasks
    else:
        create_bootstrap_from_legacy(
            runtime, essential_config, startup_channel_id, adapter_types, adapter_configs, kwargs
        )


def create_bootstrap_from_legacy(
    runtime: Any,
    essential_config: Optional[EssentialConfig],
    startup_channel_id: Optional[str],
    adapter_types: List[str],
    adapter_configs: Optional[Dict[str, AdapterConfig]],
    kwargs: JSONDict,
) -> None:
    """Create bootstrap config from legacy parameters.

    Args:
        runtime: The CIRISRuntime instance to configure
        essential_config: Optional EssentialConfig
        startup_channel_id: Optional startup channel ID
        adapter_types: List of adapter type names
        adapter_configs: Optional dict of adapter configurations
        kwargs: Additional keyword arguments
    """
    runtime.essential_config = essential_config or EssentialConfig()
    runtime.essential_config.load_env_vars()
    runtime.startup_channel_id = startup_channel_id or ""
    runtime.adapter_configs = adapter_configs or {}

    # Type narrow: kwargs.get returns JSONDict value, narrow to expected types
    modules_raw = kwargs.get("modules", [])
    runtime.modules_to_load = modules_raw if isinstance(modules_raw, list) else []
    debug_raw = kwargs.get("debug", False)
    runtime.debug = debug_raw if isinstance(debug_raw, bool) else False
    runtime._preload_tasks = []

    from ciris_engine.schemas.runtime.adapter_management import AdapterLoadRequest
    from ciris_engine.schemas.runtime.bootstrap import RuntimeBootstrapConfig

    adapter_load_requests = [
        AdapterLoadRequest(adapter_type=atype, adapter_id=atype, auto_start=True) for atype in adapter_types
    ]
    runtime.bootstrap = RuntimeBootstrapConfig(
        adapters=adapter_load_requests,
        adapter_overrides=runtime.adapter_configs,
        modules=runtime.modules_to_load,
        startup_channel_id=runtime.startup_channel_id,
        debug=runtime.debug,
        preload_tasks=runtime._preload_tasks,
    )


def check_mock_llm(runtime: Any) -> None:
    """Check for mock LLM environment variable and add to modules if needed.

    Args:
        runtime: The CIRISRuntime instance
    """
    if os.environ.get("CIRIS_MOCK_LLM", "").lower() in ("true", "1", "yes", "on"):
        logger.warning("CIRIS_MOCK_LLM environment variable detected in CIRISRuntime")
        if "mock_llm" not in runtime.modules_to_load:
            runtime.modules_to_load.append("mock_llm")
            logger.info("Added mock_llm to modules to load")


def load_adapters_from_bootstrap(runtime: Any) -> None:
    """Load adapters from bootstrap configuration.

    Args:
        runtime: The CIRISRuntime instance
    """
    from ciris_engine.logic.adapters import load_adapter
    from ciris_engine.schemas.adapters.runtime_context import AdapterStartupContext

    for load_request in runtime.bootstrap.adapters:
        try:
            adapter_class = load_adapter(load_request.adapter_type)

            # Create AdapterStartupContext
            context = AdapterStartupContext(
                essential_config=runtime.essential_config or EssentialConfig(),
                modules_to_load=runtime.modules_to_load,
                startup_channel_id=runtime.startup_channel_id or "",
                debug=runtime.debug,
                bus_manager=None,  # Will be set after initialization
                time_service=None,  # Will be set after initialization
                service_registry=None,  # Will be set after initialization
            )

            # Apply overrides if present
            config = load_request.config or AdapterConfig(adapter_type=load_request.adapter_type)
            if load_request.adapter_id in runtime.adapter_configs:
                config = runtime.adapter_configs[load_request.adapter_id]

            # Create adapter with context
            # Pass the settings as adapter_config so adapters can find them
            adapter_instance = adapter_class(runtime, context=context, adapter_config=config.settings)
            runtime.adapters.append(adapter_instance)
            logger.info(f"Successfully loaded adapter: {load_request.adapter_id}")
        except Exception as e:
            logger.error(f"Failed to load adapter '{load_request.adapter_id}': {e}", exc_info=True)
